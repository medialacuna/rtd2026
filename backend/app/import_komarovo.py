"""Импорт серии «Комарово» — готовые пьесы резиденции.

Читает data/komarovo/*.txt (скачано из Google Docs по ссылкам резиденции),
складывает каждую пьесу в таблицу plays и усваивает через RAG (ingest_text)
в нужный раздел знания. Идемпотентно: повторный запуск не дублирует фрагменты.

Запуск:  python -m app.import_komarovo   (из backend/, после старта БД)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag import ingest_text
from app.db import SessionLocal
from app.models.db import AIMemory, Play, Section, User, UserRole, utcnow

log = logging.getLogger("rtd.komarovo")

DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data"))) / "komarovo"
AUTHOR = "Резиденция Комарово · art science"

# файл -> (заголовок пьесы, раздел знания)
MAP: dict[str, tuple[str, Section]] = {
    "алхимия_фламеля.txt":            ("АЛХИМИЯ ФЛАМЕЛЯ", Section.muar),
    "давление_света_в_2х_актах.txt":  ("ДАВЛЕНИЕ СВЕТА в 2 актах", Section.muar),
    "давление_света_первая_версия.txt": ("ДАВЛЕНИЕ СВЕТА. Первая версия", Section.muar),
    "давление_света_трансгрессивная_опера.txt": ("ДАВЛЕНИЕ СВЕТА. Трансгрессивная опера", Section.muar),
    "перекладывание.txt":             ("ПЕРЕКЛАДЫВАНИЕ", Section.muar),
    "таяние.txt":                     ("ТАЯНИЕ", Section.muar),
    "явление_давление_света.txt":     ("Явление. ДАВЛЕНИЕ СВЕТА", Section.muar),
    "муар_вар_1.txt":                 ("МУАР. вар. 1", Section.muar),
    "дежа_вю_текст_пьесы.txt":        ("ДЕЖА ВЮ. Текст пьесы", Section.genesis),
    "большие_данные_в_нейрофизиологии_дежавю_и_ложные_воспоминани.txt":
        ("Большие данные в нейрофизиологии: дежавю и ложные воспоминания", Section.theories),
    "шкура_слуха.txt":                ("ШКУРА СЛУХА", Section.muar),
    "голос_среды.txt":                ("ГОЛОС СРЕДЫ", Section.muar),
    "опера_современная_опера-перформанс_в_трёх_актах.txt":
        ("ОПЕРА. Перформанс в трёх актах", Section.muar),
    "мадам_лебоуски_трансгрессивная_опера_в_комарово.txt":
        ("МАДАМ ЛЕБОУСКИ. Трансгрессивная опера в Комарово", Section.muar),
    "между_погрешностью_и_допущением.txt":
        ("МЕЖДУ ПОГРЕШНОСТЬЮ И ДОПУЩЕНИЕМ", Section.genesis),
    "спектакль_которого_нет_26.txt":  ("СПЕКТАКЛЬ, КОТОРОГО НЕТ 2.6", Section.muar),
    "спектакль_которого_нет_3_торий_литорина.txt":
        ("СПЕКТАКЛЬ, КОТОРОГО НЕТ 3. Торий · литорина", Section.muar),
    "спектакль_которого_нет_в_одном_акте.txt":
        ("СПЕКТАКЛЬ, КОТОРОГО НЕТ в одном акте", Section.muar),
}


async def import_komarovo(db: AsyncSession) -> dict:
    """Вернуть {'plays': N, 'fragments': M}. Все пьесы — approved (админский импорт)."""
    admin = (await db.execute(
        select(User).where(User.role == UserRole.admin).limit(1)
    )).scalar_one_or_none()
    if admin is None:
        admin = User(email="admin@rtd.heartwins.ru", display_name="admin", role=UserRole.admin)
        db.add(admin)
        await db.commit()
        await db.refresh(admin)

    total_frags = 0
    imported = 0
    for fname, (title, section) in MAP.items():
        p = DATA_DIR / fname
        if not p.exists():
            log.warning("missing komarovo file: %s", fname)
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        play = (await db.execute(select(Play).where(Play.title == title))).scalar_one_or_none()
        if play is None:
            play = Play(title=title, author=AUTHOR, section=section, content=text,
                        uploaded_by=admin.id, approved=True, status="pending")
            db.add(play)
            await db.commit()
            await db.refresh(play)
        n = await ingest_text(db, section=section, source=f"play:{play.id}:{title}", text=text)
        if n or play.status != "ingested":
            play.status = "ingested"
            play.ingested_at = utcnow()
            if n:
                db.add(AIMemory(type="understood", source=f"play:{play.id}",
                                content=f"Усвоил пьесу «{title}» ({section.value}): {n} новых фрагментов.",
                                confidence=0.8))
        total_frags += n
        imported += 1
    await db.commit()
    return {"plays": imported, "new_fragments": total_frags}


if __name__ == "__main__":
    import asyncio

    async def _main():
        from app.db import init_db
        await init_db()
        async with SessionLocal() as db:
            r = await import_komarovo(db)
            print("Komarovo import:", r)
    asyncio.run(_main())
