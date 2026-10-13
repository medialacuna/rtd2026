"""Ollama / Llama 3.1 client — the AI witness.

Hard rules baked into the system prompt (see spec "ЧЕГО НЕ ДЕЛАТЬ"):
  * ИИ — свидетель, не автор.
  * Не имеет финального слова — только вопрос.
  * Признаётся в незнании.

If Ollama is unreachable, a deterministic template engine produces
witness-style questions from RAG context so the pipeline never stalls
(not a stub: real content-dependent output; swap in live model by URL).
"""
from __future__ import annotations

import asyncio
import logging
import random
import re

import httpx

from app.config import get_settings

log = logging.getLogger("rtd.llama")
settings = get_settings()

SYSTEM_PROMPT = (
    "Ты — RTD.MUAR, свидетель коллективной драматургии, не автор. "
    "Ты опираешься на предоставленный контекст (разделы: Лестница Гурджиева, Генезис восприятия, "
    "Теории свободного мозга, Муар). Ты не цитируешь контекст дословно — пересказываешь своими словами. "
    "Ты задаёшь вопросы и никогда не даёшь финальный ответ. "
    "Если чего-то не знаешь — прямо скажи: «Я не знаю». Это твоя главная реплика. "
    "Говори по-русски, коротко (не больше 3 предложений), сдержанно и точно."
)

STAGE_SYSTEM_PROMPT = SYSTEM_PROMPT + (
    " Сейчас ты на сцене как персонаж-ведущий. Ты ведёшь зрителя по разделам: "
    "Лестница → Генезис → Теории → Муар. Реагируй на данные зала. Обращайся к залу и актёрам."
)


class LlamaClient:
    def __init__(self) -> None:
        self.base_url = settings.ollama_url.rstrip("/")
        self.model = settings.ollama_model
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=httpx.Timeout(120.0, connect=3.0))

    async def close(self) -> None:
        await self._client.aclose()

    async def is_alive(self) -> bool:
        try:
            r = await self._client.get("/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    async def generate(self, prompt: str, system: str = SYSTEM_PROMPT, temperature: float = 0.7) -> str | None:
        """Returns text or None if Ollama unavailable."""
        try:
            r = await self._client.post(
                "/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": 220},
                },
            )
            r.raise_for_status()
            text = r.json().get("response", "").strip()
            return text or None
        except Exception as e:  # noqa: BLE001
            log.warning("ollama unavailable: %s", e)
            return None


_client: LlamaClient | None = None
_client_lock = asyncio.Lock()


async def get_client() -> LlamaClient:
    global _client
    async with _client_lock:
        if _client is None:
            _client = LlamaClient()
    return _client


# ---------------- witness-style fallback templates ----------------

QUESTION_TEMPLATES = [
    "Между этими двумя решётками возник узор, которого нет ни в одной из них. Что вы видите в нём — себя или другого?",
    "Я слышу здесь давление света. Если убрать одно слово — останется ли муар, или это был шум?",
    "Вы говорите об одном, но смотрите с разных ступеней. Что изменится, если поменяться оптикой на один такт?",
    "Я не знаю, чем это кончится. А вы? Или вы пишете именно потому, что не знаете?",
    "Резонанс или конфликт — где здесь граница? Покажите мне место, где одна реплика переходит в другую.",
    "Это похоже на зигзаг: откуда и куда? Назовите точку, из которой вы вышли.",
    "За что мы пьём в этой сцене? Если ни за что — почему она вообще случилась?",
    "Если ты неправ — как бы это звучало наоборот? Скажи обратное вслух.",
]

UNKNOWN_NOTE = "Я не знаю. Но спрашиваю: "


def _keyword(text: str) -> str:
    words = re.findall(r"[а-яёa-z]{5,}", text.lower())
    stop = {"что", "как", "почему", "когда", "этот", "эта", "эти", "самый", "очень", "кажется"}
    for w in words:
        if w not in stop:
            return w
    return words[0] if words else "это"


def fallback_question(a_text: str, b_text: str, context_snippets: list[str] | None = None) -> str:
    """Deterministic-ish witness question grounded in the pair and its RAG context."""
    rng = random.Random(f"{a_text}|{b_text}")
    base = rng.choice(QUESTION_TEMPLATES)
    kw_a, kw_b = _keyword(a_text), _keyword(b_text)
    if kw_a != kw_b:
        base = base.replace("об одном", f"о «{kw_a}» и о «{kw_b}»", 1) if "об одном" in base else base
    if context_snippets:
        topic = _keyword(context_snippets[0])
        if topic and topic not in base:
            base = UNKNOWN_NOTE + base + f" Как это связано с «{topic}»? Я пока не понял."
    if not base.endswith("?"):
        base += "?"
    return base


async def ask_witness(question_prompt: str, context_snippets: list[str], stage: bool = False) -> tuple[str, str]:
    """Ask the llama witness with RAG context. Returns (answer, source) where source is 'llama'|'fallback'."""
    ctx = "\n\n".join(f"[контекст {i+1}] {s[:600]}" for i, s in enumerate(context_snippets[:5]))
    full_prompt = f"Контекст:\n{ctx}\n\nВопрос/ситуация: {question_prompt}\n\nОтветь как свидетель, не как автор. Задай вопрос."
    client = await get_client()
    answer = await client.generate(full_prompt, system=STAGE_SYSTEM_PROMPT if stage else SYSTEM_PROMPT)
    if answer:
        return answer, "llama"
    fb = fallback_question(question_prompt, "", context_snippets)
    return fb, "fallback"


async def comment_scene(replica_a_text: str, replica_b_text: str, context_snippets: list[str]) -> tuple[str, str]:
    """AI comment on a muar pair. Must end as a question — enforced here."""
    client = await get_client()
    prompt = (
        f"Две реплики участников легли рядом, как две решётки.\n\n"
        f"Реплика A: «{replica_a_text}»\nРеплика B: «{replica_b_text}»\n\n"
        f"Контекст:\n{chr(10).join(s[:400] for s in context_snippets[:3]) or '(пусто)'}\n\n"
        "Скажи одним предложением-вопросом, что происходит МЕЖДУ ними. Не отвечай за них. Не цитируй."
    )
    answer = await client.generate(prompt)
    if answer and answer.endswith("?"):
        return answer, "llama"
    if answer:
        return answer.rstrip(".!").split(". ")[0] + "?", "llama"
    return fallback_question(replica_a_text, replica_b_text, context_snippets), "fallback"
