"""Seed the four knowledge sections from /data markdown files.

Idempotent: re-running only adds genuinely new chunks. Also creates the
bootstrap admin user (env RTD_ADMIN_EMAIL) so /admin is reachable on day one.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag import ingest_text
from app.config import get_settings
from app.models.db import Section, User, UserRole

log = logging.getLogger("rtd.seed")
settings = get_settings()

DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data")))

SEED_FILES: list[tuple[Section, str]] = [
    (Section.lestnica, "lestnica.md"),
    (Section.genesis, "genesis.md"),
    (Section.muar, "muar.md"),
]
THEORIES_DIR = DATA_DIR / "theories"


async def seed_knowledge(db: AsyncSession) -> int:
    total = 0
    plans: list[tuple[Section, Path]] = []
    for section, fname in SEED_FILES:
        p = DATA_DIR / fname
        if p.exists():
            plans.append((section, p))
    if THEORIES_DIR.exists():
        for p in sorted(THEORIES_DIR.glob("*.md")):
            plans.append((Section.theories, p))
    for section, p in plans:
        try:
            n = await ingest_text(db, section=section, source=p.name, text=p.read_text(encoding="utf-8"))
            total += n
            if n:
                log.info("seeded %s from %s (+%d fragments)", section.value, p.name, n)
        except Exception:  # noqa: BLE001
            log.exception("seed failed for %s", p)
    # bootstrap admin
    admin_email = os.environ.get("RTD_ADMIN_EMAIL", "").strip().lower()
    if admin_email:
        u = (await db.execute(select(User).where(User.email == admin_email))).scalar_one_or_none()
        if u is None:
            db.add(User(email=admin_email, display_name="admin", role=UserRole.admin))
            await db.commit()
            log.info("bootstrap admin created: %s", admin_email)
    return total
