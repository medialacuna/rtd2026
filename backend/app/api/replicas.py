"""Replicas API — pool CRUD + muar trigger + takt rules.

Rules from spec:
  * ≤ 280 знаков, ≤ 3 реплики за такт (30 минут)
  * чужие реплики не редактируются НИКТО (update/delete only own, delete = отзыв права)
  * каждая реплика сразу уходит в муар-пайплайн и в WS-поток
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import embed
from app.ai.muar import intensity_score
from app.api.auth import current_user
from app.config import get_settings
from app.db import get_db
from app.models.db import AIMemory, Replica, Scene, User, utcnow
from app.services.scenes import process_replica_for_muar
from app.ws.hub import hub

router = APIRouter(prefix="/api/replicas", tags=["replicas"])
settings = get_settings()


class ReplicaIn(BaseModel):
    text: str = Field(min_length=1, max_length=settings.max_replica_len)
    is_tost: bool = False


def _rdict(r: Replica, user: User | None = None) -> dict:
    return {
        "id": r.id, "text": r.text, "step_level": r.step_level.value,
        "is_tost": r.is_tost, "intensity": r.intensity,
        "user_id": r.user_id, "scene_id": r.scene_id,
        "user_name": (user.display_name or user.email.split("@")[0]) if user else "?",
        "created_at": r.created_at,
    }


@router.get("")
async def list_replicas(
    sort: str = Query("fresh", pattern="^(fresh|resonant|contested)$"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Лента: свежие / резонансные (в сценах с резонансом) / спорные (высокая дистанция)."""
    q = select(Replica).order_by(Replica.id.desc()).limit(limit).offset(offset)
    if sort == "resonant":
        q = (select(Replica, Scene.resonance)
             .join(Scene, or_(Scene.replica_a_id == Replica.id, Scene.replica_b_id == Replica.id))
             .order_by(Scene.resonance.desc(), Replica.id.desc()).limit(limit).offset(offset))
    elif sort == "contested":
        q = (select(Replica, Scene.semantic_distance)
             .join(Scene, or_(Scene.replica_a_id == Replica.id, Scene.replica_b_id == Replica.id))
             .order_by(Scene.semantic_distance.desc(), Replica.id.desc()).limit(limit).offset(offset))
    rows = (await db.execute(q)).all()
    out = []
    for row in rows:
        r = row._mapping.get("Replica", row[0]) if hasattr(row, "_mapping") and "Replica" in row._mapping else (row[0] if isinstance(row, tuple) else row)
        u = await db.get(User, r.user_id)
        out.append(_rdict(r, u))
    return out


@router.post("", status_code=201)
async def create_replica(body: ReplicaIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Реплика падает в пул → эмбеддинг → муар → WS."""
    takt_start = utcnow() - timedelta(minutes=settings.takt_minutes)
    recent = (await db.execute(
        select(Replica).where(Replica.user_id == user.id, Replica.created_at >= takt_start)
    )).scalars().all()
    if len(recent) >= settings.replicas_per_takt:
        raise HTTPException(429, f"За такт ({settings.takt_minutes} мин) — до {settings.replicas_per_takt} реплик. Игра не останавливается; подожди такт.")

    vec = embed(body.text)
    rep = Replica(
        user_id=user.id, text=body.text.strip(), embedding=vec.tolist(),
        step_level=user.step_level, is_tost=body.is_tost,
        intensity=round(intensity_score(body.text), 4),
    )
    db.add(rep)
    await db.flush()
    # живая память ИИ: реплики участников тоже усваиваются (раздел replicas)
    db.add(AIMemory(type="interaction", source=f"replica:{rep.id}",
                    content=f"{user.display_name} со ступени «{user.step_level.value}»: {rep.text}",
                    confidence=0.6))
    await db.commit()

    d = _rdict(rep, user)
    await hub.broadcast("replica:new", d)
    scenes = await process_replica_for_muar(db, rep)
    return {"replica": d, "scenes": scenes}


@router.delete("/{replica_id}")
async def retract_replica(replica_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Отзыв реплики участником (права, п.6). Сцена не разрушается — перепишется без неё."""
    rep = await db.get(Replica, replica_id)
    if rep is None:
        raise HTTPException(404)
    if rep.user_id != user.id and user.role.value != "admin":
        raise HTTPException(403, "Чужие реплики не трогают. Только свои. Только своё.")
    if rep.scene_id:
        scene = await db.get(Scene, rep.scene_id)
        if scene:
            scene.ai_comment += "\n\n[Один из авторов отозвал реплику. Сцена будет переписана без неё.]"
    rep.text = "[реплика отозвана автором]"
    await db.commit()
    return {"ok": True}


@router.post("/{replica_id}/react/{scene_id}")
async def react_to_scene(replica_id: int, scene_id: int, user: User = Depends(current_user),
                        db: AsyncSession = Depends(get_db)):
    """Реагировать можно СВОЕЙ репликой рядом — это резонанс, не лайк."""
    from app.models.db import Reaction
    rep = await db.get(Replica, replica_id)
    if rep is None or rep.user_id != user.id:
        raise HTTPException(403, "Реагируй только своей репликой.")
    if (await db.execute(select(Reaction).where(Reaction.scene_id == scene_id, Reaction.user_id == user.id))).scalar_one_or_none():
        raise HTTPException(409, "Ты уже отреагировал на эту сцену.")
    db.add(Reaction(scene_id=scene_id, user_id=user.id, replica_id=replica_id))
    await db.commit()
    from app.services.scenes import rescore_resonance
    scene = await rescore_resonance(db, scene_id)
    return {"ok": True, "scene": scene}
