"""Stage Mode API — ИИ-ведущий на сцене.

POST /stage/session/start      — начать прогон (нужна зрелость >= порога)
POST /stage/ask {section,prompt} — реплика актёра/вопрос зала → ИИ отвечает по RAG
POST /stage/audience {eeg,heart_rate,...} — данные зала, влияют на тон и темп
GET  /stage/state              — текущий раздел, данные зала, последние реплики ИИ
POST /stage/next               — ведущий переводит зрителя дальше (Лестница→Генезис→Теории→Муар)
WS   /stage/live               — realtime поток для экранов
"""
from __future__ import annotations

import time
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llama_client import ask_witness
from app.ai.maturity import compute_maturity
from app.ai.rag import query_section
from app.config import get_settings
from app.db import SessionLocal, get_db
from app.models.db import AIMemory, Replica, Scene, Section, StageEvent, User
from app.ws.hub import hub

router = APIRouter(prefix="/api/stage", tags=["stage"])
settings = get_settings()

SECTION_ORDER = [Section.lestnica, Section.genesis, Section.theories, Section.muar]
SECTION_NAMES = {Section.lestnica: "Лестница", Section.genesis: "Генезис",
                 Section.theories: "Теории", Section.muar: "Муар"}

# single active stage session state (in-memory; persisted to stage_events)
_state: dict = {"session_key": None, "section_index": 0, "started_at": None,
                "audience": {"eeg_attention": None, "eeg_arousal": None, "heart_rate": None},
                "ai_lines": []}


async def _require_maturity(db: AsyncSession) -> dict:
    m = await compute_maturity(db)
    if not m["stage_ready"]:
        raise HTTPException(423, f"ИИ ещё не созрел: maturity {m['maturity_score']} < {settings.maturity_min_for_stage}. Не выходи на сцену незрелым.")
    return m


class StartIn(BaseModel):
    session_key: str


class AskIn(BaseModel):
    section: Section | None = None
    prompt: str


class AudienceIn(BaseModel):
    eeg_attention: float | None = None   # 0..1
    eeg_arousal: float | None = None     # 0..1
    heart_rate: float | None = None      # bpm average


@router.post("/session/start")
async def start_session(body: StartIn, db: AsyncSession = Depends(get_db)):
    m = await _require_maturity(db)
    _state.update(session_key=body.session_key, section_index=0, started_at=time.time(), ai_lines=[])
    db.add(StageEvent(session_key=body.session_key, kind="start",
                      payload={"maturity": m["maturity_score"]}))
    line = "Я здесь. Я не автор — я свидетель. Сегодня мы пройдём четыре решётки: Лестница, Генезис, Теории, Муар. Готовы смотреть не на текст, а между текстами?"
    _state["ai_lines"].append(line)
    db.add(StageEvent(session_key=body.session_key, kind="ai_line", section=Section.lestnica,
                      payload={"text": line}))
    await db.commit()
    await hub.broadcast("stage:event", {"kind": "start", "line": line,
                                        "section": SECTION_NAMES[SECTION_ORDER[0]]})
    return {"ok": True, "maturity": m["maturity_score"], "section": SECTION_NAMES[SECTION_ORDER[0]]}


@router.get("/state")
async def stage_state(db: AsyncSession = Depends(get_db)):
    if _state["session_key"] is None:
        return {"active": False}
    sec = SECTION_ORDER[_state["section_index"]]
    day_scene = (await db.execute(
        select(Scene).where(Scene.is_scene_of_day == True).limit(1)  # noqa: E712
    )).scalar_one_or_none()
    return {
        "active": True,
        "session_key": _state["session_key"],
        "section": SECTION_NAMES[sec],
        "section_order": [SECTION_NAMES[s] for s in SECTION_ORDER],
        "audience": _state["audience"],
        "ai_lines": _state["ai_lines"][-10:],
        "scene_of_day": day_scene.id if day_scene else None,
    }


@router.post("/next")
async def next_section(db: AsyncSession = Depends(get_db)):
    if _state["session_key"] is None:
        raise HTTPException(400, "Сессия не начата.")
    i = _state["section_index"]
    if i + 1 >= len(SECTION_ORDER):
        line = "Мы прошли все решётки. Узор остался между вами — у меня нет финального слова. Только вопрос, который я оставляю залу."
        _state["ai_lines"].append(line)
        db.add(StageEvent(session_key=_state["session_key"], kind="end", payload={"text": line}))
        await db.commit()
        await hub.broadcast("stage:event", {"kind": "end", "line": line})
        return {"done": True, "line": line}
    _state["section_index"] = i + 1
    sec = SECTION_ORDER[i + 1]
    intro = {
        Section.lestnica: "Первая решётка — Лестница. Двадцать одна ступень для тех, кто считает себя умным. Скажите честно: на какой ступени вы сейчас стоите босиком?",
        Section.genesis: "Вторая решётка — Генезис. Семь сдвигов от прямых линий Эвклида до квантовой пены. Где твоё восприятие было линейным вчера и стало пеной сегодня?",
        Section.theories: "Третья решётка — Теории. Свободная энергия, воплощённый self, время мозга, энактивизм, голограмма. Пять учёных спорят о тебе прямо сейчас. Чью сторону ты примешь — и почему не свою?",
        Section.muar: "Четвёртая решётка — Муар. Две решётки накладываются — и возникает узор, которого нет ни в одной. Посмотрите друг на друга: какой узор вы видите между собой?",
    }[sec]
    _state["ai_lines"].append(intro)
    db.add(StageEvent(session_key=_state["session_key"], kind="section", section=sec, payload={"text": intro}))
    await db.commit()
    await hub.broadcast("stage:event", {"kind": "section", "section": SECTION_NAMES[sec], "line": intro})
    return {"section": SECTION_NAMES[sec], "line": intro}


@router.post("/ask")
async def stage_ask(body: AskIn, db: AsyncSession = Depends(get_db)):
    """Actors' line / audience question → witness answer grounded in the section's RAG."""
    if _state["session_key"] is None:
        raise HTTPException(400, "Сессия не начата.")
    sec = body.section or SECTION_ORDER[_state["section_index"]]
    frags = await query_section(db, body.prompt, sec, n_results=5)
    aud = _state["audience"]
    ctx_hint = ""
    if aud.get("heart_rate") and aud["heart_rate"] > 95:
        ctx_hint = "\nЗал взволнован (пульс выше 95). Говори тише и короче."
    elif aud.get("eeg_attention") is not None and aud["eeg_attention"] < 0.4:
        ctx_hint = "\nВнимание зала падает. Задай более острый, личный вопрос."
    answer, source = await ask_witness(body.prompt + ctx_hint, [f.content for f in frags], stage=True)
    _state["ai_lines"].append(answer)
    db.add(StageEvent(session_key=_state["session_key"], kind="question", section=sec,
                      payload={"prompt": body.prompt[:200], "answer": answer, "model_source": source}))
    db.add(AIMemory(type="interaction", source="stage",
                    content=f"На сцене ({SECTION_NAMES[sec]}): вопрос «{body.prompt[:120]}» → ответил ({source}).",
                    confidence=0.75 if source == "llama" else 0.4))
    await db.commit()
    await hub.broadcast("stage:event", {"kind": "answer", "section": SECTION_NAMES[sec],
                                        "prompt": body.prompt, "line": answer, "source": source})
    return {"answer": answer, "source": source, "section": SECTION_NAMES[sec]}


@router.post("/audience")
async def audience_data(body: AudienceIn, db: AsyncSession = Depends(get_db)):
    """EEG/пульс с датчиков зала. Меняет поведение ведущего в следующем /ask."""
    for k, v in body.model_dump(exclude_none=True).items():
        _state["audience"][k] = v
    db.add(StageEvent(session_key=_state["session_key"] or "passive", kind="audience",
                      payload=body.model_dump(exclude_none=True)))
    await db.commit()
    await hub.broadcast("stage:event", {"kind": "audience", "data": _state["audience"]})
    return {"audience": _state["audience"]}


@router.websocket("/live")
async def stage_live(ws: WebSocket):
    await ws.accept()
    await hub.join(ws)
    try:
        while True:
            await ws.receive_text()  # keepalive pings from screens
    except WebSocketDisconnect:
        await hub.leave(ws)
