"""Scenes & muar-map API."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import embed
from app.api.auth import current_user
from app.db import get_db
from app.models.db import Replica, Scene, StepLevel, User
from app.services.scenes import _scene_dict, pick_scene_of_day, settle_royalties
from app.config import get_settings

router = APIRouter(prefix="/api/scenes", tags=["scenes"])
settings = get_settings()


@router.get("")
async def list_scenes(limit: int = Query(30, le=100), offset: int = 0,
                      db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    q = select(Scene).order_by(Scene.created_at.desc()).limit(limit).offset(offset)
    scenes = (await db.execute(q)).scalars().all()
    out = []
    for s in scenes:
        # «скрытое»: сцены таинства видны только нужным ступеням
        if s.hidden_for_step is not None and user.step_level != s.hidden_for_step:
            continue
        d = await _scene_dict(db, s)
        out.append(d)
    return out


@router.get("/day")
async def scene_of_day(db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(Scene).where(Scene.is_scene_of_day == True))).scalar_one_or_none()  # noqa: E712
    if s is None:
        return await pick_scene_of_day(db) or {}
    return await _scene_dict(db, s)


@router.post("/day/refresh")
async def refresh_scene_of_day(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    if user.role.value != "admin":
        raise HTTPException(403, "Только админ (обычно — по расписанию worker-а).")
    d = await pick_scene_of_day(db)
    return d or {}


@router.get("/{scene_id}")
async def get_scene(scene_id: int, db: AsyncSession = Depends(get_db)):
    s = await db.get(Scene, scene_id, populate_existing=True)
    if s is None:
        raise HTTPException(404)
    return await _scene_dict(db, s)


@router.post("/{scene_id}/stage")
async def stage_scene(scene_id: int, pot: int = Query(100, ge=1, le=10000),
                      db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    """Сцена идёт в постановку → роялти поровну авторам реплик (Heartwins)."""
    if user.role.value != "admin":
        raise HTTPException(403, "Постановку назначает админ/DAO.")
    rows = await settle_royalties(db, scene_id, pot)
    if not rows:
        raise HTTPException(404, "Сцена не найдена.")
    return {"ok": True, "royalties": rows}


@router.get("/muar/map")
async def muar_map(db: AsyncSession = Depends(get_db)):
    """Муар-карта: узлы — реплики (с координатами из эмбеддинга через PCA-lite),
    рёбра — сцены (вес = толщина, тип = цвет). Кто с кем резонирует / конфликтует."""
    scenes = (await db.execute(select(Scene).order_by(Scene.weight.desc()).limit(200))).scalars().all()
    replica_ids: set[int] = set()
    edges = []
    for s in scenes:
        replica_ids.update([s.replica_a_id, s.replica_b_id])
        edges.append({
            "source": s.replica_a_id, "target": s.replica_b_id,
            "weight": s.weight, "distance": s.semantic_distance,
            "coherence": s.coherence, "resonance": s.resonance, "scene_id": s.id,
        })
    reps = (await db.execute(select(Replica).where(Replica.id.in_(replica_ids or {0})))).scalars().all()
    users = {u.id: u for u in (await db.execute(select(User))).scalars().all()}
    # 2D projection: first two principal dims via cheap SVD on embedding matrix
    nodes = []
    if reps:
        mat = np.array([r.embedding for r in reps], dtype=np.float64)
        try:
            _, _, vt = np.linalg.svd(mat - mat.mean(axis=0), full_matrices=False)
            proj = (mat - mat.mean(axis=0)) @ vt[:2].T
        except np.linalg.LinAlgError:
            proj = mat[:, :2]
        by_id = {}
        for r, (x, y) in zip(reps, proj):
            u = users.get(r.user_id)
            by_id[r.id] = {
                "id": r.id, "x": round(float(x), 3), "y": round(float(y), 3),
                "text": r.text[:120], "step": r.step_level.value,
                "user_name": (u.display_name or u.email.split("@")[0]) if u else "?",
                "intensity": r.intensity,
            }
        nodes = list(by_id.values())
    return {"nodes": nodes, "edges": edges}
