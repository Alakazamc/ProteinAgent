"""Protein knowledge retrieval module — lightweight offline-friendly RAG."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DATA_PATH = Path(__file__).resolve().parent / "data" / "protein_knowledge.jsonl"
DEFAULT_BACKEND = "local-hash"
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
HASH_VECTOR_DIM = 256
TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")


@dataclass(frozen=True)
class RetrievedChunk:
    """A single knowledge chunk returned by the retrieval engine."""

    text: str
    source: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "source": self.source, "score": round(self.score, 4)}


@dataclass
class _KnowledgeEntry:
    text: str
    source: str
    category: str


class ProteinKnowledgeBase:
    """Knowledge base for protein-domain RAG."""

    def __init__(
        self,
        data_path: str | Path | None = None,
        backend: str = DEFAULT_BACKEND,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self._data_path = Path(data_path) if data_path else DEFAULT_DATA_PATH
        self._requested_backend = (backend.strip().lower() if backend else DEFAULT_BACKEND)
        self._embedding_model_name = embedding_model
        self._entries: list[_KnowledgeEntry] = []
        self._entry_vectors: list[list[float]] = []
        self._model: Any = None
        self._backend_name = "disabled"
        self._ready = False

        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def search(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        """Return the *top_k* most relevant knowledge chunks for *query*."""
        if not self._ready or not query.strip() or top_k <= 0:
            return []

        try:
            query_vector = self._encode_query(query)
        except Exception:
            logger.exception("Knowledge base search failed")
            return []

        if not query_vector:
            return []

        scored: list[tuple[float, int]] = []
        for idx, entry_vector in enumerate(self._entry_vectors):
            score = _dot(query_vector, entry_vector)
            if self._backend_name == DEFAULT_BACKEND and score <= 0:
                continue
            scored.append((score, idx))

        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[RetrievedChunk] = []
        for score, idx in scored[: min(top_k, len(scored))]:
            entry = self._entries[idx]
            results.append(
                RetrievedChunk(text=entry.text, source=entry.source, score=float(score))
            )
        return results

    def list_entries(self) -> list[dict[str, str]]:
        """Return a summary of all loaded knowledge entries."""
        return [
            {"text": e.text[:120], "source": e.source, "category": e.category}
            for e in self._entries
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> None:
        self._entries = self._read_jsonl(self._data_path)
        if not self._entries:
            logger.warning("No knowledge entries loaded from %s", self._data_path)
            return

        if self._requested_backend == "sentence-transformer":
            if self._load_sentence_transformer_vectors():
                return
            logger.warning(
                "sentence-transformer backend unavailable locally; falling back to local-hash."
            )

        self._load_local_hash_vectors()

    def _encode_query(self, query: str) -> list[float]:
        if self._backend_name == "sentence-transformer" and self._model is not None:
            vector = self._model.encode([query], normalize_embeddings=True)[0]
            return [float(item) for item in vector]
        return _hash_embed(query)

    def _load_local_hash_vectors(self) -> None:
        self._entry_vectors = [_hash_embed(entry.text) for entry in self._entries]
        self._backend_name = DEFAULT_BACKEND
        self._ready = True
        logger.info("Knowledge base ready with local-hash backend: %d entries", len(self._entries))

    def _load_sentence_transformer_vectors(self) -> bool:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
        except Exception:
            return False

        try:
            self._model = SentenceTransformer(
                self._embedding_model_name,
                local_files_only=True,
            )
        except TypeError:
            logger.warning(
                "Installed sentence-transformers does not support local_files_only; "
                "falling back to local-hash."
            )
            return False
        except Exception:
            return False

        embeddings = self._model.encode(
            [entry.text for entry in self._entries],
            normalize_embeddings=True,
        )
        self._entry_vectors = [[float(item) for item in vector] for vector in embeddings]
        self._backend_name = "sentence-transformer"
        self._ready = True
        logger.info(
            "Knowledge base ready with sentence-transformer backend: %d entries",
            len(self._entries),
        )
        return True

    @staticmethod
    def _read_jsonl(path: Path) -> list[_KnowledgeEntry]:
        if not path.exists():
            logger.warning("Knowledge file not found: %s", path)
            return []

        entries: list[_KnowledgeEntry] = []
        for line_number, raw_line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                entries.append(
                    _KnowledgeEntry(
                        text=obj["text"],
                        source=obj.get("source", "unknown"),
                        category=obj.get("category", "general"),
                    )
                )
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("Skipping line %d in %s: %s", line_number, path, exc)
        return entries


def get_cached_knowledge_base(
    data_path: str | Path | None = None,
    backend: str = DEFAULT_BACKEND,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> ProteinKnowledgeBase:
    resolved_path = str((Path(data_path) if data_path else DEFAULT_DATA_PATH).resolve())
    normalized_backend = backend.strip().lower() or DEFAULT_BACKEND
    normalized_model = embedding_model.strip() or DEFAULT_EMBEDDING_MODEL
    return _build_cached_knowledge_base(resolved_path, normalized_backend, normalized_model)


@lru_cache(maxsize=8)
def _build_cached_knowledge_base(
    resolved_path: str,
    backend: str,
    embedding_model: str,
) -> ProteinKnowledgeBase:
    return ProteinKnowledgeBase(
        data_path=resolved_path,
        backend=backend,
        embedding_model=embedding_model,
    )


def _hash_embed(text: str, dim: int = HASH_VECTOR_DIM) -> list[float]:
    features = _collect_features(text)
    if not features:
        return []

    vector = [0.0] * dim
    for feature in features:
        bucket = _stable_bucket(feature, dim)
        vector[bucket] += 1.0

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return []
    return [value / norm for value in vector]


def _collect_features(text: str) -> list[str]:
    normalized_text = " ".join(TOKEN_PATTERN.findall(text.lower()))
    tokens = TOKEN_PATTERN.findall(normalized_text)
    features: list[str] = []
    for token in tokens:
        features.append(f"tok:{token}")
        token_chars = token if len(token) <= 64 else token[:64]
        for n in (2, 3):
            if len(token_chars) < n:
                continue
            for index in range(len(token_chars) - n + 1):
                features.append(f"ng{n}:{token_chars[index:index + n]}")
    return features


def _stable_bucket(feature: str, dim: int) -> int:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % dim


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))
