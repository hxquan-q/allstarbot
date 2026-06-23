"""Vector-similarity candidate ranking for schema retrieval.

Pure logic: given a query embedding and a list of candidates (each carrying an
embedding vector and arbitrary metadata), score by cosine similarity, drop
those below ``min_similarity``, sort descending and cap at ``top_k``. The
similarity function is injectable so tests (and future ANN backends) can swap
it; the default reuses the existing numpy ``batch_cosine_similarity``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from apps.datasource.embedding.utils import batch_cosine_similarity

DEFAULT_MIN_SIMILARITY = 0.3
DEFAULT_TOP_K = 10


@dataclass(frozen=True)
class ScoredCandidate:
    """A candidate ranked against the query."""

    id: Any
    score: float
    meta: dict = field(default_factory=dict)


class CandidateRanker:
    def __init__(
        self,
        *,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        top_k: int = DEFAULT_TOP_K,
        similarity_fn: Optional[Callable] = None,
    ):
        self.min_similarity = min_similarity
        self.top_k = top_k
        self._similarity = similarity_fn or batch_cosine_similarity

    def rank(self, query_embedding, candidates: list[dict]) -> list[ScoredCandidate]:
        if not candidates:
            return []

        indexed = []
        doc_vecs = []
        for candidate in candidates:
            embedding = candidate.get("embedding")
            if not embedding:
                continue
            indexed.append(candidate)
            doc_vecs.append(embedding)

        if not indexed:
            return []

        similarities = self._similarity(query_embedding, doc_vecs)

        scored = []
        for candidate, score in zip(indexed, similarities, strict=True):
            if score >= self.min_similarity:
                meta = {k: v for k, v in candidate.items() if k != "embedding"}
                scored.append(ScoredCandidate(id=candidate.get("id"), score=float(score), meta=meta))

        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[: self.top_k]
