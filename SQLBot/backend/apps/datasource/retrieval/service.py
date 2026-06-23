"""RetrievalService — orchestration glue over the retrieval pure modules.

Turns :class:`CandidateRanker` + :class:`RelationGraph` + :class:`ContextPacker`
into a usable "describe the schema for this question" pipeline:

1. embed the question;
2. rank table candidates by vector similarity (drop below threshold, cap top-k);
3. expand the hit set with FK **sphere** neighbours and inter-hit **bridge**
   tables so multi-table joins remain possible (a low-relevance table that sits
   on the join path between two hits is pulled in);
4. token-budget-pack schema / examples / docs / samples into a
   :class:`BuildContext`.

All dependencies are injected (``embed_fn``, ``packer``; ``ranker`` optional),
so the service is unit-testable with synthetic embeddings and graphs. The live
wiring (Phase 2) supplies a real embedding model + table provider + the
datasource's ``table_relation`` graph; until ``embedding_vector`` is populated
the ranker also works over legacy JSON embeddings loaded by the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from apps.datasource.retrieval.fk_expander import RelationGraph
from apps.datasource.retrieval.packer import BuildContext, ContextPacker
from apps.datasource.retrieval.ranker import CandidateRanker


@dataclass
class TableCandidate:
    table_name: str
    embedding: Optional[list] = None
    m_schema: str = ""
    id: Any = None
    extra: dict = field(default_factory=dict)


@dataclass
class RetrievalConfig:
    min_similarity: float = 0.3
    top_k: int = 10
    sphere_radius: int = 1
    max_bridge_hops: int = 6


class RetrievalService:
    def __init__(
        self,
        embed_fn: Callable,
        *,
        config: Optional[RetrievalConfig] = None,
        packer: ContextPacker,
        ranker: Optional[CandidateRanker] = None,
    ):
        self.embed_fn = embed_fn
        self.config = config or RetrievalConfig()
        self.packer = packer
        self.ranker = ranker or CandidateRanker(
            min_similarity=self.config.min_similarity, top_k=self.config.top_k
        )

    def build_context(
        self,
        question: str,
        candidates: list,
        relation_graph: Optional[RelationGraph],
        examples: list,
        terminology: list,
        samples: list,
    ) -> BuildContext:
        query_embedding = self.embed_fn(question) if question else None

        scored = []
        if query_embedding is not None and candidates:
            cand_dicts = [
                {
                    "id": c.id,
                    "table_name": c.table_name,
                    "embedding": c.embedding,
                    "m_schema": c.m_schema,
                }
                for c in candidates
            ]
            scored = self.ranker.rank(query_embedding, cand_dicts)

        # hits in rank order (drop anything without a table name)
        hit_names = [s.meta.get("table_name") for s in scored if s.meta.get("table_name")]
        hit_set = set(hit_names)

        # expand with FK sphere + inter-hit bridges so joins stay possible
        if relation_graph is not None and hit_set:
            required = relation_graph.required_tables(
                hit_set,
                sphere_radius=self.config.sphere_radius,
                max_bridge_hops=self.config.max_bridge_hops,
            )
        else:
            required = set(hit_set)

        # schema strings: hits first (rank order), then bridges/sphere
        by_name = {c.table_name: c for c in candidates}
        schema_items: list = []
        added: set = set()
        for name in hit_names:
            if name in by_name and name not in added:
                schema_items.append(by_name[name].m_schema)
                added.add(name)
        for name in required:
            if name in by_name and name not in added:
                schema_items.append(by_name[name].m_schema)
                added.add(name)

        channels = {
            "schema": schema_items,
            "examples": list(examples),
            "docs": list(terminology),
            "samples": list(samples),
        }
        return self.packer.pack(channels)


def build_default_packer_from_settings() -> ContextPacker:
    """Build a ContextPacker whose budgets come from settings (lazy import)."""
    from common.core.config import settings

    return ContextPacker(
        channel_budgets={
            "schema": settings.RETRIEVAL_SCHEMA_TOKEN_BUDGET,
            "examples": settings.RETRIEVAL_EXAMPLES_TOKEN_BUDGET,
            "docs": settings.RETRIEVAL_DOCS_TOKEN_BUDGET,
            "samples": settings.RETRIEVAL_SAMPLES_TOKEN_BUDGET,
        },
        total_budget=settings.RETRIEVAL_TOTAL_TOKEN_BUDGET,
    )


def build_retrieval_service_from_settings(embed_fn: Callable) -> RetrievalService:
    """Wire-only convenience: a RetrievalService configured from settings.

    The caller still supplies ``embed_fn`` (the embedding model) and the
    per-request candidates + relation graph at call time.
    """
    from common.core.config import settings

    return RetrievalService(
        embed_fn,
        config=RetrievalConfig(
            min_similarity=settings.RETRIEVAL_MIN_SIMILARITY,
            top_k=settings.RETRIEVAL_TOP_K,
            sphere_radius=settings.RETRIEVAL_SPHERE_RADIUS,
            max_bridge_hops=settings.RETRIEVAL_MAX_BRIDGE_HOPS,
        ),
        packer=build_default_packer_from_settings(),
    )
