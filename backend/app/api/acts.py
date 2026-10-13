"""Acts API — читать, скачивать, ставить."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import current_user
from app.db import get_db
from app.models.db import Act, Scene, User
from app.services.scenes import _scene_dict, assemble_act

router = APIRouter(prefix="/api/acts", tags=["acts"])


@router.get("")
async def list_acts(db: AsyncSession = Depends(get_db)):
    acts = (await db.execute(select(Act).order_by(Act.id.desc()))).scalars().all()
    return [{"id": a.id, "title": a.title, "theme": a.theme, "season": a.season,
             "published_at": a.published_at,
             "scenes_count": len((await db.execute(select(Scene).where(Scene.act_id == a.id))).scalars().all())}
            for a in acts]


@router.post("")
async def create_act(theme: str = Query("", max_length=80),
                     db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    """Неделя пришла — ИИ собирает лучшие unpublished сцены в акт."""
    if user.role.value != "admin":
        raise HTTPException(403, "Акт собирает админ (обычно — worker по расписанию).")
    d = await assemble_act(db, theme)
    if d is None:
        raise HTTPException(400, "Нет непубликованных сцен. Пишите — я соединяю.")
    return d


@router.get("/{act_id}")
async def get_act(act_id: int, db: AsyncSession = Depends(get_db)):
    act = await db.get(Act, act_id)
    if act is None:
        raise HTTPException(404)
    scenes = (await db.execute(select(Scene).where(Scene.act_id == act_id).order_by(Scene.weight.desc()))).scalars().all()
    body = [await _scene_dict(db, s) for s in scenes]
    return {"id": act.id, "title": act.title, "theme": act.theme, "season": act.season,
            "published_at": act.published_at, "scenes": body}


@router.get("/{act_id}/download", response_class=PlainTextResponse)
async def download_act(act_id: int, fmt: str = Query("md", pattern="^(md|txt)$"), db: AsyncSession = Depends(get_db)):
    """Акт — это уже пьеса. Её можно читать. Скачать. Поставить."""
    act = await db.get(Act, act_id)
    if act is None:
        raise HTTPException(404)
    scenes = (await db.execute(select(Scene).where(Scene.act_id == act_id).order_by(Scene.weight.desc()))).scalars().all()
    lines = [f"# {act.title}", f"_тема: {act.theme}_", ""]
    for i, s in enumerate(scenes, 1):
        a, b = s.replica_a, s.replica_b
        ua = await db.get(User, a.user_id); ub = await db.get(User, b.user_id)
        na = (ua.display_name or ua.email.split("@")[0]); nb = (ub.display_name or ub.email.split("@")[0])
        lines += [f"## Сцена {i} (вес муара {s.weight:.2f})",
                  f"**{na}** ({a.step_level.value}): {a.text}",
                  "",
                  f"*ИИ:* {s.ai_comment}",
                  "",
                  f"**{nb}** ({b.step_level.value}): {b.text}", ""]
    return "\n".join(lines)
