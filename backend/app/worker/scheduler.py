"""Background worker: game clock cycles + memory digest + nightly LoRA scheduling.

Replaces Celery beat with asyncio tasks (same semantics for single-VPS deploy;
swap to celery if you split hosts — task bodies are importable functions).
  * every takt end: nothing destructive, pool keeps flowing
  * every hour: scene of the day refresh (24h cycle)
  * daily 00:05: AI digest «что понял / не понял / спросил»
  * weekly Mon 03:00: build mature dataset + schedule LoRA
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.ai.maturity import compute_maturity
from app.config import get_settings
from app.db import SessionLocal
from app.models.db import AIMemory, utcnow
from app.services.scenes import assemble_act, pick_scene_of_day
from app.worker.train_lora import collect_mature_dataset, schedule_lora_run

log = logging.getLogger("rtd.worker")
settings = get_settings()


async def scene_of_day_loop() -> None:
    while True:
        try:
            async with SessionLocal() as db:
                d = await pick_scene_of_day(db)
                if d:
                    log.info("scene of the day -> #%s weight=%s", d["id"], d["weight"])
        except Exception:  # noqa: BLE001
            log.exception("scene_of_day_loop")
        await asyncio.sleep(3600)


async def digest_loop() -> None:
    """Daily: «Что я понял. Что я не понял. Что спросил». Writes into ai_memory."""
    while True:
        now = datetime.now(timezone.utc)
        nxt = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
        if now.hour < 1:
            nxt = now.replace(hour=0, minute=5, second=0, microsecond=0)
        await asyncio.sleep((nxt - now).total_seconds())
        try:
            async with SessionLocal() as db:
                from sqlalchemy import select
                recent = (await db.execute(select(AIMemory).order_by(AIMemory.id.desc()).limit(120))).scalars().all()
                asked = [m for m in recent if m.type == "asked"]
                understood = [m for m in recent if m.type == "understood"]
                lost = [m for m in recent if m.type in ("not_understood", "interaction")]
                lines = ["Что я понял: " + ("; ".join(m.content[:90] for m in understood[:3]) or "пока ничего нового. Я жду.")]
                lines.append(f"Что я не понял: {len(lost)} реплик остались без пары или ушли в шум.")
                if asked:
                    lines.append("Что я спросил: " + " | ".join(m.content.split("Спросил: ")[-1][:80] for m in asked[:3]))
                db.add(AIMemory(type="digest", source="worker-daily", content="\n".join(lines), confidence=0.65))
                await db.commit()
                log.info("daily digest written")
        except Exception:  # noqa: BLE001
            log.exception("digest_loop")


async def weekly_lora_loop() -> None:
    while True:
        now = datetime.now(timezone.utc)
        days_ahead = (0 - now.weekday()) % 7 or 7   # next Monday
        nxt = (now + timedelta(days=days_ahead)).replace(hour=3, minute=0, second=0, microsecond=0)
        await asyncio.sleep((nxt - now).total_seconds())
        try:
            async with SessionLocal() as db:
                job = await schedule_lora_run(db)
                log.info("weekly LoRA scheduled: %s (%s samples)", job["id"], job["dataset"]["samples"])
        except Exception:  # noqa: BLE001
            log.exception("weekly_lora_loop")


async def act_loop() -> None:
    """Weekly act assembly right after LoRA slot (Monday ~03:30)."""
    while True:
        now = datetime.now(timezone.utc)
        days_ahead = (0 - now.weekday()) % 7 or 7
        nxt = (now + timedelta(days=days_ahead)).replace(hour=3, minute=30, second=0, microsecond=0)
        await asyncio.sleep((nxt - now).total_seconds())
        try:
            async with SessionLocal() as db:
                a = await assemble_act(db)
                if a:
                    log.info("act assembled: %s (%s scenes)", a["title"], len(a["scene_ids"]))
        except Exception:  # noqa: BLE001
            log.exception("act_loop")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    from app.db import init_db
    await init_db()
    log.info("RTD.MUAR worker started (scene-of-day / digest / weekly-lora / weekly-act)")
    await asyncio.gather(scene_of_day_loop(), digest_loop(), weekly_lora_loop(), act_loop())


if __name__ == "__main__":
    asyncio.run(main())
