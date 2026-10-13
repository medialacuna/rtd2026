"""Публичная библиотека пьес — «Комарово» и всё, что усвоил портал.

GET /api/plays          — список (без полного текста)
GET /api/plays/{id}     — текст пьесы для чтения
GET /api/plays/{id}/fragments — сколько фрагментов усвоено ИИ в каком разделе
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.db import Fragment, Play

router = APIRouter(prefix="/api/plays", tags=["plays"])


@router.get("")
async def list_plays(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Play).order_by(Play.id))).scalars().all()
    out = []
    for p in rows:
        frags = (await db.execute(
            select(func.count(Fragment.id)).where(Fragment.source.like(f"play:{p.id}:%"))
        )).scalar_one()
        out.append({
            "id": p.id, "title": p.title, "author": p.author,
            "section": p.section.value, "status": p.status,
            "approved": p.approved, "votes_for": p.votes_for, "votes_against": p.votes_against,
            "chars": len(p.content), "learned_fragments": frags,
            "ingested_at": p.ingested_at, "created_at": p.created_at,
            "excerpt": p.content.strip().replace("\n\n", " ")[:220],
        })
    return out


@router.get("/{play_id}")
async def get_play(play_id: int, db: AsyncSession = Depends(get_db)):
    p = await db.get(Play, play_id)
    if p is None:
        raise HTTPException(404)
    return {"id": p.id, "title": p.title, "author": p.author, "section": p.section.value,
            "content": p.content, "ingested_at": p.ingested_at}
