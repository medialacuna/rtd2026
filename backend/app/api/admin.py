"""Admin API — загрузка пьес и идей, разделы знания, метрика зрелости, DAO-голосование.

Форма загрузки: PDF / DOCX / Markdown → чанкинг → эмбеддинг → векторная база.
ИИ усваивает текст сразу (RAG уровень 1); кнопка «Обучить» ставит ночной LoRA-прогон.
"""
from __future__ import annotations

import io
import logging
from datetime import timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.maturity import compute_maturity
from app.ai.rag import ingest_text, query_section
from app.api.auth import current_user
from app.db import get_db
from app.models.db import AIMemory, Fragment, Play, Section, User, UserRole, utcnow
from app.worker.train_lora import schedule_lora_run

log = logging.getLogger("rtd.admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])


async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(403, "Нужна роль админа.")
    return user


def _extract_text(filename: str, raw: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            return "\n\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"PDF не читается ({e}). Приложи markdown/txt.")
    if name.endswith(".docx"):
        try:
            import docx
            d = docx.Document(io.BytesIO(raw))
            return "\n\n".join(p.text for p in d.paragraphs)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"DOCX не читается ({e}).")
    return raw.decode("utf-8", errors="replace")


class SectionStats(BaseModel):
    pass


@router.get("/sections")
async def sections_stats(db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    rows = (await db.execute(
        select(Fragment.section, func.count(Fragment.id), func.max(Fragment.learned_at)).group_by(Fragment.section)
    )).all()
    return [{"section": s.value, "fragments": c, "last_learned": m} for s, c, m in rows]


@router.post("/upload")
async def upload_play(
    title: str = Form(...),
    author: str = Form(""),
    section: Section = Form(...),
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Загрузить пьесу/идею. Админ — сразу в раздел. Автор — на DAO-голосование."""
    if user.role not in (UserRole.admin, UserRole.author):
        raise HTTPException(403, "Предложить текст может роль «автор» или админ.")
    if file is not None:
        content = _extract_text(file.filename, await file.read())
    elif text:
        content = text
    else:
        raise HTTPException(400, "Нужен файл (pdf/docx/md) или поле text.")
    if len(content.strip()) < 50:
        raise HTTPException(400, "Слишком короткий текст — ИИ нечему учиться.")

    play = Play(title=title, author=author, section=section, content=content,
                uploaded_by=user.id, approved=(user.role == UserRole.admin),
                status="pending")
    db.add(play)
    await db.commit()
    if play.approved:
        n = await ingest_text(db, section=play.section, source=f"play:{play.id}:{play.title}", text=play.content)
        play.status = "ingested"
        play.ingested_at = utcnow()
        db.add(AIMemory(type="understood", source=f"play:{play.id}",
                        content=f"Усвоил «{play.title}» ({section.value}): {n} новых фрагментов.", confidence=0.7))
        await db.commit()
        return {"play_id": play.id, "learned_fragments": n, "status": "ingested"}
    return {"play_id": play.id, "status": "awaiting_vote", "learned_fragments": 0}


class VoteIn(BaseModel):
    play_id: int
    vote: int  # +1 / -1


@router.post("/vote")
async def dao_vote(body: VoteIn, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    """DAO решает, принять предложение автора или нет. Голос участника = 1 (+токены как вес)."""
    play = await db.get(Play, body.play_id)
    if play is None:
        raise HTTPException(404)
    if body.vote not in (-1, 1):
        raise HTTPException(400)
    weight = 1 + min(user.tokens_balance // 100, 3)   # Heartwins: приоритет в голосовании
    if body.vote == 1:
        play.votes_for += weight
    else:
        play.votes_against += weight
    decision_needed = play.votes_for + play.votes_against >= 5
    result = None
    if decision_needed and not play.approved:
        if play.votes_for > play.votes_against:
            play.approved = True
            n = await ingest_text(db, section=play.section, source=f"play:{play.id}:{play.title}", text=play.content)
            play.status = "ingested"; play.ingested_at = utcnow()
            result = {"accepted": True, "learned_fragments": n}
        elif play.votes_against >= 2 * play.votes_for:
            play.approved = False; play.status = "rejected"
            result = {"accepted": False}
    await db.commit()
    return {"votes_for": play.votes_for, "votes_against": play.votes_against, "decision": result}


@router.get("/plays")
async def list_plays(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    plays = (await db.execute(select(Play).order_by(Play.id.desc()))).scalars().all()
    return [{"id": p.id, "title": p.title, "author": p.author, "section": p.section.value,
             "status": p.status, "approved": p.approved, "votes_for": p.votes_for,
             "votes_against": p.votes_against, "uploaded_by": p.uploaded_by,
             "ingested_at": p.ingested_at} for p in plays]


@router.get("/maturity")
async def maturity(db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    """maturity_score 0..100. К премьере нужен >= 75."""
    return await compute_maturity(db)


@router.post("/train")
async def train(db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    """Кнопка «Обучить»: собирает зрелые реплики в датасет, ставит ночной LoRA-прогон."""
    job = await schedule_lora_run(db)
    return job


@router.get("/ai/log")
async def ai_log(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Публичная страница /ai: что ИИ спрашивал, понял, не понял."""
    rows = (await db.execute(select(AIMemory).order_by(AIMemory.id.desc()).limit(min(limit, 200)))).scalars().all()
    return [{"id": m.id, "type": m.type, "content": m.content, "source": m.source,
             "confidence": m.confidence, "learned_at": m.learned_at} for m in rows]
