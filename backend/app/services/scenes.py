"""Scene service — the muar pipeline.

On every new replica:
  1. embed it
  2. find nearest pool candidates (cos sim >= floor)
  3. compute drama weight; above threshold -> create scene with AI question-comment
  4. broadcast scene:new over WS, log into ai_memory (Level 3: память постоянно)

Also: scene of the day, resonance re-scoring, act assembly, royalties.
"""
from __future__ import annotations

import logging
from datetime import timedelta

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llama_client import comment_scene
from app.ai.muar import compute_drama_weight
from app.ai.rag import query_section
from app.config import get_settings
from app.models.db import (
    AIMemory, Act, Reaction, Replica, Royalty, Scene, User, as_utc, utcnow,
)
from app.ws.hub import hub

log = logging.getLogger("rtd.scenes")
settings = get_settings()


async def _scene_dict(db: AsyncSession, scene: Scene) -> dict:
    async def side(rep: Replica | None):
        if rep is None:
            return None
        u = await db.get(User, rep.user_id)
        return {
            "id": rep.id, "text": rep.text, "step_level": rep.step_level.value,
            "user_id": rep.user_id, "user_name": (u.display_name or u.email.split("@")[0]) if u else "?",
            "created_at": rep.created_at,
        }
    return {
        "id": scene.id,
        "replica_a": await side(scene.replica_a),
        "replica_b": await side(scene.replica_b),
        "ai_comment": scene.ai_comment,
        "semantic_distance": scene.semantic_distance,
        "coherence": scene.coherence,
        "weight": scene.weight,
        "resonance": scene.resonance,
        "is_scene_of_day": scene.is_scene_of_day,
        "act_id": scene.act_id,
        "created_at": scene.created_at,
    }


async def process_replica_for_muar(db: AsyncSession, new_replica: Replica) -> list[dict]:
    """Modules 5+3: embed -> pair -> weight -> scene -> broadcast."""
    emb_new = np.array(new_replica.embedding, dtype=np.float64)

    pool = (await db.execute(
        select(Replica).where(Replica.id != new_replica.id)
        .order_by(Replica.id.desc()).limit(500)
    )).scalars().all()

    created: list[dict] = []
    used_other: set[int] = set()
    for other in pool:
        emb_o = np.array(other.embedding, dtype=np.float64)
        sim = float(np.dot(emb_new, emb_o))
        if sim < 0.70:      # spec: find_similar(threshold=0.7)
            continue
        if other.user_id == new_replica.user_id:
            continue        # муар рождается МЕЖДУ разными решётками; себя с собой не соединяем
        m = compute_drama_weight(emb_new, emb_o, new_replica.text, other.text)
        if m["weight"] < settings.scene_weight_threshold or m["kind"] == "noise":
            continue
        pair_exists = (await db.execute(
            select(Scene).where(
                Scene.replica_a_id.in_([new_replica.id, other.id]),
                Scene.replica_b_id.in_([new_replica.id, other.id]),
                Scene.replica_a_id != Scene.replica_b_id,
            )
        )).first()
        if pair_exists or other.id in used_other:
            continue
        used_other.add(other.id)

        ctx_frags = await query_section(db, f"{new_replica.text} {other.text}", None, n_results=3)
        comment, source = await comment_scene(new_replica.text, other.text, [f.content for f in ctx_frags])

        scene = Scene(
            replica_a_id=other.id, replica_b_id=new_replica.id,
            ai_comment=comment,
            semantic_distance=m["semantic_distance"], coherence=m["coherence"],
            weight=m["weight"], resonance=0,
        )
        db.add(scene)
        await db.flush()
        new_replica.scene_id = scene.id
        if other.scene_id is None:
            other.scene_id = scene.id

        # Level 3 memory: every AI interaction is logged
        db.add(AIMemory(
            type="asked", source=f"scene:{scene.id}",
            content=f"Соединил реплики {other.id}×{new_replica.id} (вес {m['weight']}). Спросил: {comment}",
            confidence=0.8 if source == "llama" else 0.5,
        ))
        await db.commit()
        scene.replica_a, scene.replica_b = other, new_replica
        d = await _scene_dict(db, scene)
        d["muar"] = m
        await hub.broadcast("scene:new", d)
        created.append(d)
        if len(created) >= 2:   # одна новая реплика рождает максимум 2 сцены за такт
            break
    return created


async def rescore_resonance(db: AsyncSession, scene_id: int) -> dict | None:
    """Resonance grows when participants react with their OWN replicas nearby. Re-weight."""
    scene = await db.get(Scene, scene_id, populate_existing=True)
    if scene is None:
        return None
    count = len((await db.execute(
        select(Reaction).where(Reaction.scene_id == scene_id)
    )).scalars().all())
    scene.resonance = count
    m = compute_drama_weight(
        np.array(scene.replica_a.embedding, dtype=np.float64),
        np.array(scene.replica_b.embedding, dtype=np.float64),
        scene.replica_a.text, scene.replica_b.text, resonance=count,
    )
    scene.weight, scene.semantic_distance, scene.coherence = m["weight"], m["semantic_distance"], m["coherence"]
    await db.commit()
    d = await _scene_dict(db, scene)
    await hub.broadcast("scene:update", d)
    return d


async def pick_scene_of_day(db: AsyncSession) -> dict | None:
    """24h cycle: highest-weight scene becomes scene of the day."""
    since = utcnow() - timedelta(hours=24)
    all_scenes = (await db.execute(
        select(Scene).order_by(Scene.weight.desc()).limit(200)
    )).scalars().all()
    scenes = [x for x in all_scenes if as_utc(x.created_at) >= since] or all_scenes[:5]
    if not scenes:
        return None
    await db.execute(update(Scene).values(is_scene_of_day=False))
    best = scenes[0]
    best.is_scene_of_day = True
    db.add(AIMemory(type="understood", source=f"scene:{best.id}",
                    content=f"Сцена дня #{best.id}: вес {best.weight}. Я показал её всем. Не комментировал — спросил."))
    await db.commit()
    await db.refresh(best)
    d = await _scene_dict(db, best)
    await hub.broadcast("scene:day", d)
    return d


async def assemble_act(db: AsyncSession, theme: str = "") -> dict | None:
    """Week cycle: top unpublished scenes by weight+resonance become an act."""
    scenes = (await db.execute(
        select(Scene).where(Scene.act_id.is_(None)).order_by(Scene.weight.desc(), Scene.resonance.desc()).limit(8)
    )).scalars().all()
    if not scenes:
        return None
    n_acts = len((await db.execute(select(Act))).scalars().all())
    act = Act(title=f"Акт {n_acts + 1}. {theme or 'Муар недели'}", theme=theme or "муар",
              season="", published_at=utcnow())
    db.add(act)
    await db.flush()
    toasts = []
    for s in scenes:
        s.act_id = act.id
        for rid in (s.replica_a_id, s.replica_b_id):
            rep = await db.get(Replica, rid)
            if rep and rep.is_tost:
                toasts.append(rep.text)
    await db.commit()
    monolog = "\n".join(toasts[-5:]) if toasts else ""
    return {
        "id": act.id, "title": act.title, "theme": act.theme,
        "scene_ids": [s.id for s in scenes],
        "closing_monolog_from_toasts": monolog,
        "published_at": act.published_at,
    }


async def settle_royalties(db: AsyncSession, scene_id: int, pot: int = 100) -> list[dict]:
    """Постановка сцены: роялти поровну между авторами реплик. Heartwins."""
    scene = await db.get(Scene, scene_id, populate_existing=True)
    if scene is None:
        return []
    authors = list({scene.replica_a.user_id, scene.replica_b.user_id})
    share = pot // max(len(authors), 1)
    out = []
    for uid in authors:
        u = await db.get(User, uid)
        u.tokens_balance += share
        db.add(Royalty(scene_id=scene.id, user_id=uid, amount=share, note=f"постановка сцены {scene.id}"))
        out.append({"user_id": uid, "email": u.email, "amount": share})
    await db.commit()
    return out
