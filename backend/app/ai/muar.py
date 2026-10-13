"""Мьюар — алгоритм драматургического веса.

Вес = (Семантическое расстояние × Интенсивность × Резонанс аудитории) / Согласованность
  * Семантическое расстояние — косинус между эмбеддингами реплик.
  * Интенсивность — длина, эмоциональная плотность, вопросы, капс, тост.
  * Резонанс — сколько участников отреагировали своими репликами рядом.
  * Согласованность — «об одном ли» (лексическое пересечение). Ноль → шум,
    сто → скучно. Делим на мягкую функцию согласованности с пиком посередине:
    высший вес — когда реплики об одном, но говорят разное. Это и есть муар.
"""
from __future__ import annotations

import math
import re

import numpy as np

from app.ai.embeddings import STOPWORDS, _normalize, embed

_QUESTION_RE = re.compile(r"[?!…]{1,}")
_CAPS_WORD = re.compile(r"\b[А-ЯЁA-Z]{3,}\b")
_EMOTIONAL = {
    "ненавижу", "боюсь", "страх", "люблю", "боль", "крик", "тишина", "свобода",
    "свет", "тьма", "кровь", "вода", "огонь", "память", "забвение", "правда",
    "ложь", "невозможно", "выпьем", "тост", "умру", "жив", "мертв", "бессмерт",
}


def intensity_score(text: str) -> float:
    """0..1 — length, emotion density, questions, shouting."""
    t = text.strip()
    if not t:
        return 0.0
    length = min(len(t) / 180.0, 1.0)                       # longer (up to ~280) = more committed
    questions = min(len(_QUESTION_RE.findall(t)) * 0.18, 0.5)
    lowered = t.lower()
    emotion = min(sum(1 for w in _EMOTIONAL if w in lowered) * 0.15, 0.45)
    shout = min(len(_CAPS_WORD.findall(t)) * 0.1, 0.2)
    return max(0.05, min(length * 0.35 + questions * 0.3 + emotion * 0.4 + shout * 0.2 + 0.1, 1.0))


def coherence_score(a_text: str, b_text: str) -> float:
    """0..1 — how much the replicas are ABOUT THE SAME (lexical overlap, tf-idf-lite)."""
    wa = {w for w in _normalize(a_text).split() if w not in STOPWORDS and len(w) > 3}
    wb = {w for w in _normalize(b_text).split() if w not in STOPWORDS and len(w) > 3}
    if not wa or not wb:
        return 0.0
    inter = len(wa & wb)
    jaccard = inter / len(wa | wb)
    containment = inter / min(len(wa), len(wb))
    return min(1.0, 0.5 * jaccard * 4 + 0.5 * containment * 2)  # scaled: small overlaps still count


def coherence_factor(coh: float) -> float:
    """Denominator: penalizes noise (coh≈0) AND boredom (coh≈1). Peak at coh≈0.35."""
    return 0.25 + 4.0 * ((coh - 0.35) ** 2) + 0.4


def resonance_factor(resonance: int) -> float:
    """Audience reacted with their own replicas nearby. Saturates at 8."""
    return 1.0 + 0.9 * (1.0 - math.exp(-resonance / 3.0))


def compute_drama_weight(
    emb_a: np.ndarray,
    emb_b: np.ndarray,
    text_a: str,
    text_b: str,
    resonance: int = 0,
) -> dict:
    # cosine distance for L2-normalized vectors in [0, 2] -> normalize to 0..1
    sem_distance = float(np.clip(1.0 - np.dot(emb_a, emb_b), 0.0, 2.0)) / 2.0
    ia = intensity_score(text_a)
    ib = intensity_score(text_b)
    intensity = (ia + ib) / 2.0
    coh = coherence_score(text_a, text_b)
    res = resonance_factor(resonance)
    weight = (sem_distance * intensity * res) / coherence_factor(coh)
    weight = float(np.clip(weight, 0.0, 1.0))
    kind = "noise" if coh < 0.05 else ("boredom" if coh > 0.85 and sem_distance < 0.15 else
                                       ("resonance" if sem_distance < 0.35 else
                                        ("muar" if sem_distance >= 0.35 and coh >= 0.15 else "conflict")))
    return {
        "semantic_distance": round(sem_distance, 4),
        "intensity": round(intensity, 4),
        "coherence": round(coh, 4),
        "resonance": resonance,
        "weight": round(weight, 4),
        "kind": kind,
    }


def find_muar_pairs(new_id: int, new_emb: np.ndarray, new_text: str,
                    pool: list[tuple[int, np.ndarray, str]],
                    threshold: float = 0.6,
                    candidate_similarity_floor: float = 0.7) -> list[dict]:
    """Spec Module 5: find nearest in pool (cos sim >= floor => distance <= 1-floor),
    score drama weight, return pairs above threshold sorted by weight desc."""
    out = []
    for other_id, other_emb, other_text in pool:
        if other_id == new_id:
            continue
        sim = float(np.dot(new_emb, other_emb))
        if sim < candidate_similarity_floor:
            continue  # far-far pairs are pure noise, skip
        m = compute_drama_weight(new_emb, other_emb, new_text, other_text)
        if m["weight"] >= threshold:
            m["other_id"] = other_id
            out.append(m)
    out.sort(key=lambda m: m["weight"], reverse=True)
    return out
