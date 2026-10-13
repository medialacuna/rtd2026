"""Зрелость ИИ (maturity_score, 0..100).

maturity = retrieval_accuracy*40 + replica_quality*30 + memory_depth*30
  * retrieval_accuracy — RAG self-probe (rag.retrieval_accuracy)
  * replica_quality — доля «зрелых» реплик в пуле (попавшие в сцены с весом >= порога,
                     нормированная на покрытие базы знаний и активность)
  * memory_depth — объём и разнообразие ai_memory (типы + дневные сводки)
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag import retrieval_accuracy
from app.config import get_settings
from app.models.db import AIMemory, Fragment, Replica, Scene

settings = get_settings()


async def compute_maturity(db: AsyncSession) -> dict:
    acc = await retrieval_accuracy(db)

    total_replicas = (await db.execute(select(func.count(Replica.id)))).scalar() or 0
    mature_ids = set()
    scenes_q = await db.execute(
        select(Scene.replica_a_id, Scene.replica_b_id).where(Scene.weight >= settings.scene_weight_threshold)
    )
    for a, b in scenes_q.all():
        mature_ids.add(a); mature_ids.add(b)
    all_scenes = (await db.execute(select(func.count(Scene.id)))).scalar() or 0
    frag_count = (await db.execute(select(func.count(Fragment.id)))).scalar() or 0

    if total_replicas:
        engaged = len(mature_ids)
        quality_raw = min(engaged / max(total_replicas * 0.35, 1), 1.0)  # 35% engaged = full marks
    else:
        quality_raw = 0.0
    # knowledge coverage bonus: an AI that read the four sections is more mature
    coverage = min(frag_count / 80.0, 1.0)
    replica_quality = 0.7 * quality_raw + 0.3 * coverage

    mem_rows = (await db.execute(
        select(AIMemory.type, func.count(AIMemory.id)).group_by(AIMemory.type)
    )).all()
    mem_total = sum(c for _, c in mem_rows)
    mem_types = len({t for t, _ in mem_rows})
    digests = next((c for t, c in mem_rows if t == "digest"), 0)
    memory_depth = min(
        0.4 * min(mem_total / 50.0, 1.0) + 0.3 * min(mem_types / 5.0, 1.0) + 0.3 * min(digests / 7.0, 1.0),
        1.0,
    )

    maturity = round(100.0 * (acc * 0.4 + replica_quality * 0.3 + memory_depth * 0.3), 1)
    return {
        "maturity_score": maturity,
        "retrieval_accuracy": round(acc, 3),
        "replica_quality": round(replica_quality, 3),
        "memory_depth": round(memory_depth, 3),
        "stats": {
            "fragments": frag_count,
            "replicas": total_replicas,
            "scenes": all_scenes,
            "mature_replicas": len(mature_ids),
            "memories": mem_total,
        },
        "stage_ready": maturity >= settings.maturity_min_for_stage,
        "formula": "maturity = retrieval_accuracy*0.4 + replica_quality*0.3 + memory_depth*0.3",
    }
