"""RAG retrieval layer for schema-aware SQL generation.

Pure-logic core (no live DB / pgvector / LLM required to import or unit-test):

* :class:`CandidateRanker` – vector-similarity ranking with threshold + top-k.
* :class:`RelationGraph`  – FK-sphere expansion + shortest-path join-bridge
  discovery so multi-table joins stay possible.
* :class:`ContextPacker`  – token-budgeted, prioritised three-channel packing
  (schema / examples / docs / samples) — keeps large schemas in context.
* :class:`PgvectorSchemaStore` – builds the pgvector ``<=>`` similarity SQL for
  table / datasource / column search (pgvector imported lazily by callers).

See docs/superpowers/specs/2026-06-23-allstarbot-foundation-rebuild-design.md
(§3B) for the design. Wiring into the chat pipeline (replacing the numpy-JSON
table/datasource embedding path in apps/datasource/embedding/) lands in Phase 2
alongside the agent core.
"""
from apps.datasource.retrieval.fk_expander import RelationGraph
from apps.datasource.retrieval.packer import (
    BuildContext,
    ContextPacker,
    PackedChannel,
    default_token_counter,
)
from apps.datasource.retrieval.pgvector_store import PgvectorSchemaStore
from apps.datasource.retrieval.ranker import (
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_TOP_K,
    CandidateRanker,
    ScoredCandidate,
)
from apps.datasource.retrieval.service import (
    RetrievalConfig,
    RetrievalService,
    TableCandidate,
    build_default_packer_from_settings,
    build_retrieval_service_from_settings,
)

__all__ = [
    "BuildContext",
    "CandidateRanker",
    "ContextPacker",
    "DEFAULT_MIN_SIMILARITY",
    "DEFAULT_TOP_K",
    "PgvectorSchemaStore",
    "PackedChannel",
    "RelationGraph",
    "RetrievalConfig",
    "RetrievalService",
    "ScoredCandidate",
    "TableCandidate",
    "build_default_packer_from_settings",
    "build_retrieval_service_from_settings",
    "default_token_counter",
]
