"""AI-facing API for /muar page & RAG answers (any logged-in user).

GET  /api/ai/ask?question=...&section=muar   — RAG-ответ свидетеля с цитатами-контекстом
GET  /api/ai/memory                          — лог ИИ для страницы /ai
POST /api/ai/digest                          — дневная сводка «что понял / не понял / спросил»
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llama_client import ask_witness
from app.ai.rag import ask_ai, query_section
from app.api.auth import current_user
from app.db import get_db
from app.models.db import AIMemory, Section, User

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/ask")
async def ai_ask(question: str = Query(min_length=3, max_length=2000),
                 section: Section | None = None,
                 db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return await ask_ai(db, question, section)


@router.get("/memory")
async def ai_memory(limit: int = Query(60, le=200), mem_type: str | None = None,
                    db: AsyncSession = Depends(get_db)):
    q = select(AIMemory).order_by(AIMemory.id.desc()).limit(limit)
    if mem_type:
        q = q.where(AIMemory.type == mem_type)
    rows = (await db.execute(q)).scalars().all()
    return [{"id": m.id, "type": m.type, "content": m.content, "source": m.source,
             "confidence": m.confidence, "learned_at": m.learned_at} for m in rows]


@router.post("/digest")
async def daily_digest(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    """Уровень 3 памяти: раз в день — «Что я понял. Что я не понял. Что спросил»."""
    if user.role.value not in ("admin", "ai"):
        raise HTTPException(403, "Сводку пишет админ или worker по расписанию.")
    recent = (await db.execute(
        select(AIMemory).order_by(AIMemory.id.desc()).limit(120)
    )).scalars().all()
    asked = [m for m in recent if m.type == "asked"]
    understood = [m for m in recent if m.type == "understood"]
    lost = [m for m in recent if m.type in ("not_understood", "interaction")]
    lines = []
    if understood:
        lines.append("Что я понял: " + "; ".join(m.content[:90] for m in understood[:3]))
    else:
        lines.append("Что я понял: пока ничего нового. Я жду.")
    lines.append(f"Что я не понял: {len(lost)} реплик остались без пары или ушли в шум. Я не знаю, почему они молчат друг о друге.")
    if asked:
        lines.append("Что я спросил: " + " | ".join(m.content.split("Спросил: ")[-1][:80] for m in asked[:3]))
    digest = "\n".join(lines)
    db.add(AIMemory(type="digest", source="daily", content=digest, confidence=0.65))
    await db.commit()
    return {"digest": digest}
