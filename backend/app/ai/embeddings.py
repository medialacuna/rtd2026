"""Embeddings for the muar algorithm.

Two providers:
  1. SentenceTransformers — paraphrase-multilingual-mpnet-base-v2 (768 dim).
     Used automatically if the package is installed and model available (offline cache ok).
  2. Hashing fallback — deterministic character n-gram bag hashed into N dims.
     No dependencies, works offline, Russian-friendly (n-grams, not words),
     cosine-similar for paraphrase / distant for conflict. Good enough to drive
     the muar pipeline; swap in ST or pgvector in prod without touching callers.

Vector store: fragments + replica embeddings live in Postgres JSON columns here;
in production they are mirrored to ChromaDB/pgvector (see docker-compose + README).
"""
from __future__ import annotations

import hashlib
import math
import re
import threading
from functools import lru_cache

import numpy as np

from app.config import get_settings

settings = get_settings()
DIM = settings.embedding_dim

_st_lock = threading.Lock()
_st_model = None
_st_tried = False


def _try_sentence_transformers():
    global _st_model, _st_tried
    if _st_tried:
        return _st_model
    with _st_lock:
        if _st_tried:
            return _st_model
        _st_tried = True
        try:
            from sentence_transformers import SentenceTransformer
            _st_model = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")
        except Exception:
            _st_model = None
    return _st_model


# ---------------- hashing fallback ----------------

_NORM = re.compile(r"[^а-яёa-z0-9]+")

STOPWORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все",
    "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по",
    "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из",
    "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли", "если", "уже", "или",
    "ни", "быть", "был", "него", "до", "ней", "ко", "лучше", "какой", "этом", "одном",
    "можно", "при", "твой", "який", "него", "этот", "этого", "потому", "этой",
    "before", "the", "and", "of", "to", "in", "is", "it", "that", "for",
}


def _normalize(text: str) -> str:
    return _NORM.sub(" ", text.lower()).strip()


def _ngrams(text: str, n: int = 3) -> list[str]:
    """Character 3-grams over normalized words joined by spaces — robust to morphology."""
    grams = []
    for word in _normalize(text).split():
        padded = f"{word} "
        for i in range(max(1, len(padded) - n + 1)):
            grams.append(padded[i:i + n])
    return grams


def _hash_embed_one(text: str) -> np.ndarray:
    vec = np.zeros(DIM, dtype=np.float64)
    norm = _normalize(text)
    # word-level signed hashing with sublinear tf
    from collections import Counter
    tokens = [t for t in norm.split() if t not in STOPWORDS]
    for tok, tf in Counter(tokens).items():
        h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
        idx = h % DIM
        sign = 1.0 if (h >> 63) & 1 else -1.0
        vec[idx] += sign * (1.0 + math.log(tf))
    # char-trigram hashing gives fuzzy morphological overlap for Russian
    for g in _ngrams(text):
        h = int.from_bytes(hashlib.blake2b(g.encode(), digest_size=8).digest(), "big")
        idx = h % DIM
        sign = 1.0 if (h >> 63) & 1 else -1.0
        vec[idx] += 0.5 * sign
    nrm = np.linalg.norm(vec)
    if nrm == 0:
        # degenerate text -> stable pseudo-random vector so it still sits somewhere
        rng = np.random.default_rng(int.from_bytes(hashlib.blake2b(norm.encode(), digest_size=8).digest(), "big"))
        vec = rng.standard_normal(DIM)
        nrm = np.linalg.norm(vec)
    return vec / nrm


def embed_texts(texts: list[str]) -> list[np.ndarray]:
    st = _try_sentence_transformers()
    if st is not None:
        arr = st.encode(texts, normalize_embeddings=True)
        return [np.asarray(v, dtype=np.float64) for v in arr]
    return [_hash_embed_one(t) for t in texts]


@lru_cache(maxsize=4096)
def _embed_cached(text: str) -> tuple[float, ...]:
    return tuple(embed_texts([text])[0].tolist())


def embed(text: str) -> np.ndarray:
    return np.array(_embed_cached(text), dtype=np.float64)


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Vectors are L2-normalized => cosine similarity = dot product."""
    return float(1.0 - np.dot(a, b))
