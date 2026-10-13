"""RAG over the four knowledge sections.

Chunking -> embedding -> fragments table (local vector store; mirrored to
ChromaDB/pgvector in prod). Query returns top-k snippets per section.
Also holds retrieval self-test used by the maturity metric.
"""
from __future__ import annotations

import re

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import embed, embed_texts
from app.models.db import Fragment, Section

_SECTION_TITLES = {
    Section.lestnica: "Лестница",
    Section.genesis: "Генезис",
    Section.theories: "Теории",
    Section.muar: "Муар",
    Section.replicas: "Пул реплик",
}


def chunk_markdown(text: str, max_chars: int = 900, overlap: int = 120) -> list[str]:
    """Split by markdown headings/paragraphs, then window long blocks with overlap."""
    blocks: list[str] = []
    for part in re.split(r"\n\s*\n", text):
        part = part.strip()
        if not part:
            continue
        if len(part) <= max_chars:
            blocks.append(part)
        else:
            start = 0
            while start < len(part):
                blocks.append(part[start:start + max_chars].strip())
                start += max_chars - overlap
    return [b for b in blocks if b]


async def ingest_text(
    db: AsyncSession,
    *,
    section: Section,
    source: str,
    text: str,
    skip_duplicates: bool = True,
) -> int:
    """Chunk + embed + store. Returns number of new fragments learned."""
    chunks = chunk_markdown(text)
    if not chunks:
        return 0
    vectors = embed_texts(chunks)
    existing_sources = set(
        (await db.execute(select(Fragment.source).where(Fragment.section == section))).scalars().all()
    )
    if skip_duplicates and source in existing_sources:
        # re-ingest only genuinely new chunks of an updated document
        old_contents = set(
            (await db.execute(
                select(Fragment.content).where(Fragment.section == section, Fragment.source == source)
            )).scalars().all()
        )
    else:
        old_contents = set()

    added = 0
    for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
        if skip_duplicates and chunk in old_contents:
            continue
        db.add(Fragment(
            section=section, source=source, chunk_index=idx,
            content=chunk, embedding=vec.tolist(),
        ))
        added += 1
    await db.commit()
    return added


async def query_section(
    db: AsyncSession,
    question: str,
    section: Section | None = None,
    n_results: int = 5,
) -> list[Fragment]:
    """Top-k fragments by cosine similarity within section(s)."""
    stmt = select(Fragment)
    if section is not None:
        stmt = stmt.where(Fragment.section == section)
    frags = (await db.execute(stmt)).scalars().all()
    if not frags:
        return []
    qv = embed(question)
    scored: list[tuple[float, Fragment]] = []
    for f in frags:
        fv = np.array(f.embedding, dtype=np.float64)
        scored.append((float(np.dot(qv, fv)), f))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [f for _, f in scored[:n_results]]


async def ask_ai(db: AsyncSession, question: str, context_section: Section | None = None) -> dict:
    """Spec-level API: RAG query -> prompt -> llama witness answer."""
    from app.ai.llama_client import ask_witness

    frags = await query_section(db, question, context_section, n_results=5)
    snippets = [f.content for f in frags]
    answer, source = await ask_witness(question, snippets, stage=False)
    return {
        "answer": answer,
        "source": source,
        "context": [
            {"section": f.section.value, "title": _SECTION_TITLES.get(f.section, ""), "source": f.source,
             "snippet": f.content[:300]}
            for f in frags
        ],
    }


async def retrieval_accuracy(db: AsyncSession) -> float:
    """Self-probe: can the retriever find a known fragment when asked about it?

    Takes sample fragments, forms a query from their first sentence,
    checks that the same fragment appears in top-3. Real metric, no mocking.
    """
    frags = (await db.execute(select(Fragment).order_by(Fragment.id).limit(60))).scalars().all()
    if len(frags) < 5:
        return 0.0
    hits = 0
    tried = 0
    for f in frags[:30]:
        probe = f.content.split(".")[0][:160]
        if len(probe) < 20:
            continue
        results = await query_section(db, probe, f.section, n_results=3)
        tried += 1
        if any(r.id == f.id for r in results):
            hits += 1
    return hits / tried if tried else 0.0
