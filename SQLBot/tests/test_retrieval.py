"""Tests for the RAG retrieval layer (apps.datasource.retrieval).

Pure-logic modules (ranker / fk_expander / packer) are tested with synthetic
embeddings, graphs and token counters — no live database, no pgvector, no LLM.
The pgvector adapter is tested for the SQL it builds (shape only).
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import pytest  # noqa: E402

from apps.datasource.retrieval import (  # noqa: E402
    BuildContext,
    CandidateRanker,
    ContextPacker,
    PgvectorSchemaStore,
    RelationGraph,
    ScoredCandidate,
)


# --------------------------------------------------------------------------- #
# CandidateRanker
# --------------------------------------------------------------------------- #
class TestCandidateRanker:
    def test_ranks_by_cosine_similarity_desc(self):
        ranker = CandidateRanker(min_similarity=0.0, top_k=10)
        query = [1.0, 0.0]
        candidates = [
            {"id": "orthogonal", "embedding": [0.0, 1.0]},   # sim 0.0
            {"id": "same", "embedding": [1.0, 0.0]},         # sim 1.0
            {"id": "half", "embedding": [0.7071, 0.7071]},   # sim ~0.7071
        ]
        ranked = ranker.rank(query, candidates)
        assert [r.id for r in ranked] == ["same", "half", "orthogonal"]
        assert ranked[0].score == pytest.approx(1.0)
        assert ranked[1].score == pytest.approx(0.7071, abs=1e-3)

    def test_filters_below_min_similarity(self):
        ranker = CandidateRanker(min_similarity=0.5, top_k=10)
        query = [1.0, 0.0]
        candidates = [
            {"id": "low", "embedding": [0.0, 1.0]},      # 0.0  -> dropped
            {"id": "high", "embedding": [1.0, 0.0]},     # 1.0  -> kept
        ]
        ranked = ranker.rank(query, candidates)
        assert [r.id for r in ranked] == ["high"]

    def test_top_k_caps_results(self):
        ranker = CandidateRanker(min_similarity=0.0, top_k=2)
        query = [1.0, 0.0]
        candidates = [
            {"id": f"c{i}", "embedding": [1.0, float(i) * 0.001]} for i in range(5)
        ]
        ranked = ranker.rank(query, candidates)
        assert len(ranked) == 2

    def test_skips_candidates_without_embedding(self):
        ranker = CandidateRanker(min_similarity=0.0, top_k=10)
        ranked = ranker.rank([1.0, 0.0], [
            {"id": "good", "embedding": [1.0, 0.0]},
            {"id": "noemb", "embedding": None},
            {"id": "empty", "embedding": []},
            {"id": "missing"},
        ])
        assert [r.id for r in ranked] == ["good"]

    def test_preserves_metadata_on_scored_candidate(self):
        ranker = CandidateRanker(min_similarity=0.0, top_k=10)
        ranked = ranker.rank([1.0, 0.0], [
            {"id": 42, "embedding": [1.0, 0.0], "table_name": "orders", "schema": "public"},
        ])
        assert ranked[0].id == 42
        assert ranked[0].meta["table_name"] == "orders"

    def test_empty_candidates_returns_empty(self):
        assert CandidateRanker().rank([1.0, 0.0], []) == []


# --------------------------------------------------------------------------- #
# RelationGraph (FK expansion + join-bridge discovery)
# --------------------------------------------------------------------------- #
class TestRelationGraph:
    def test_from_pairs_builds_undirected_adjacency(self):
        g = RelationGraph.from_pairs([("orders", "customers"), ("orders", "products")])
        assert g.neighbors("orders") == {"customers", "products"}
        assert g.neighbors("customers") == {"orders"}  # undirected

    def test_expand_sphere_one_hop(self):
        g = RelationGraph.from_pairs([("a", "b"), ("b", "c"), ("c", "d")])
        # hits {a}; 1-hop sphere = {b}
        assert g.expand_sphere({"a"}, radius=1) == {"b"}
        # hits {b}; 1-hop sphere = {a, c}
        assert g.expand_sphere({"b"}, radius=1) == {"a", "c"}

    def test_expand_sphere_excludes_hits(self):
        g = RelationGraph.from_pairs([("a", "b")])
        assert g.expand_sphere({"a", "b"}, radius=1) == set()

    def test_bridge_tables_finds_intermediate_join(self):
        # a - c - b : a and b are hits, c is the bridge
        g = RelationGraph.from_pairs([("a", "c"), ("c", "b")])
        bridges = g.bridge_tables({"a", "b"}, max_hops=6)
        assert bridges == {"c"}

    def test_bridge_tables_multi_hop(self):
        # a - x - y - b
        g = RelationGraph.from_pairs([("a", "x"), ("x", "y"), ("y", "b")])
        assert g.bridge_tables({"a", "b"}, max_hops=6) == {"x", "y"}

    def test_bridge_tables_respects_max_hops(self):
        # a - x - y - z - b  (4 hops); max_hops=2 -> no bridge
        g = RelationGraph.from_pairs([("a", "x"), ("x", "y"), ("y", "z"), ("z", "b")])
        assert g.bridge_tables({"a", "b"}, max_hops=2) == set()
        assert g.bridge_tables({"a", "b"}, max_hops=6) == {"x", "y", "z"}

    def test_bridge_tables_direct_neighbors_not_counted_as_bridges(self):
        # a - b : direct neighbors, no intermediate bridge
        g = RelationGraph.from_pairs([("a", "b")])
        assert g.bridge_tables({"a", "b"}, max_hops=6) == set()

    def test_bridge_tables_disconnected_returns_empty(self):
        g = RelationGraph.from_pairs([("a", "x"), ("b", "y")])
        assert g.bridge_tables({"a", "b"}, max_hops=6) == set()

    def test_required_tables_unions_hits_sphere_and_bridges(self):
        # hits {a,b}; sphere of a={c}; bridge a-b = {x} via a-x-b
        g = RelationGraph.from_pairs([("a", "c"), ("a", "x"), ("x", "b")])
        required = g.required_tables({"a", "b"}, sphere_radius=1, max_bridge_hops=6)
        assert {"a", "b", "c", "x"} <= required


# --------------------------------------------------------------------------- #
# ContextPacker (token-budgeted three-channel packing)
# --------------------------------------------------------------------------- #
def _word_counter(text: str) -> int:
    """Deterministic token counter for tests: one token per whitespace word."""
    return len(text.split())


class TestContextPacker:
    def _packer(self, channel_budgets, total_budget, priority=None):
        return ContextPacker(
            channel_budgets=channel_budgets,
            total_budget=total_budget,
            priority=priority,
            token_counter=_word_counter,
        )

    def test_packs_all_when_within_budgets(self):
        packer = self._packer({"schema": 10, "examples": 5}, total_budget=100)
        ctx = packer.pack({"schema": ["a b c", "d e"], "examples": ["x y"]})
        assert ctx.channels[0].name == "schema"
        assert ctx.channels[0].items == ["a b c", "d e"]
        assert ctx.channels[0].tokens == 5
        assert ctx.channels[0].truncated is False
        assert ctx.total_tokens == 7

    def test_respects_per_channel_budget(self):
        packer = self._packer({"schema": 2}, total_budget=100)
        ctx = packer.pack({"schema": ["one two", "three four", "five"]})
        # channel budget 2 -> only first item (2 tokens) fits; rest truncated
        schema = ctx.channels[0]
        assert schema.items == ["one two"]
        assert schema.truncated is True

    def test_respects_total_budget_across_channels(self):
        packer = self._packer(
            {"schema": 100, "examples": 100}, total_budget=3, priority=["schema", "examples"]
        )
        ctx = packer.pack({"schema": ["a b"], "examples": ["c d e f"]})
        # total budget 3: schema takes 2, examples get 1 token -> "c" only
        assert ctx.total_tokens <= 3
        assert ctx.channels[0].items == ["a b"]
        # examples channel truncated to fit remaining budget
        assert ctx.channels[1].truncated is True

    def test_priority_order_honored(self):
        packer = self._packer(
            {"schema": 100, "samples": 100}, total_budget=2, priority=["samples", "schema"]
        )
        ctx = packer.pack({"schema": ["s1"], "samples": ["p q"]})
        names = [c.name for c in ctx.channels]
        assert names.index("samples") < names.index("schema")
        # samples packed first under the tight total budget
        assert ctx.channels[0].items == ["p q"]

    def test_truncated_flag_false_when_everything_fits(self):
        packer = self._packer({"schema": 10}, total_budget=100)
        ctx = packer.pack({"schema": ["a b c"]})
        assert ctx.channels[0].truncated is False

    def test_empty_channels_produce_empty_context(self):
        packer = self._packer({"schema": 10}, total_budget=100)
        ctx = packer.pack({"schema": []})
        assert ctx.total_tokens == 0
        assert ctx.channels[0].items == []

    def test_build_context_text_joins_channels(self):
        packer = self._packer({"schema": 10, "examples": 10}, total_budget=100)
        ctx = packer.pack({"schema": ["ddl one"], "examples": ["q: select 1"]})
        text = ctx.text()
        assert "ddl one" in text
        assert "q: select 1" in text

    def test_item_too_large_for_channel_is_skipped_not_partial(self):
        # a single item bigger than channel budget is dropped (no partial items)
        packer = self._packer({"schema": 2}, total_budget=100)
        ctx = packer.pack({"schema": ["huge item list here with many words"]})
        assert ctx.channels[0].items == []
        assert ctx.channels[0].truncated is True


# --------------------------------------------------------------------------- #
# PgvectorSchemaStore (SQL shape — no execution, no pgvector import needed)
# --------------------------------------------------------------------------- #
class TestPgvectorSchemaStore:
    def test_imports_without_pgvector_installed(self):
        # merely constructing must not require pgvector
        store = PgvectorSchemaStore(dim=1536)
        assert store.dim == 1536

    def test_search_tables_sql_uses_cosine_operator_and_limit(self):
        store = PgvectorSchemaStore(dim=8)
        sql, params = store.search_tables_sql(
            [0.0] * 8, ds_id=7, min_similarity=0.35, top_k=12,
        )
        assert "<=>" in sql                       # pgvector cosine distance
        assert ":embedding" in sql                # parameterised vector
        assert "core_table" in sql                # real table name
        assert "ds_id" in sql                     # real scope column
        assert "LIMIT 12" in sql
        assert "0.35" in sql                      # threshold inlined
        assert params["ds_id"] == 7
        assert params["embedding"] == [0.0] * 8

    def test_search_tables_sql_optional_ds_filter(self):
        store = PgvectorSchemaStore(dim=8)
        sql_scoped, p_scoped = store.search_tables_sql([0.0] * 8, ds_id=3, top_k=5)
        sql_open, p_open = store.search_tables_sql([0.0] * 8, ds_id=None, top_k=5)
        # scoped query references the ds_id filter and param; open does not
        assert "ds_id = :ds_id" in sql_scoped
        assert "ds_id" in p_scoped
        assert "ds_id" not in p_open

    def test_search_datasources_sql_shape(self):
        store = PgvectorSchemaStore(dim=8)
        sql, params = store.search_datasources_sql([0.0] * 8, oid=2, top_k=8)
        assert "<=>" in sql
        assert "core_datasource" in sql
        assert "oid" in sql
        assert "LIMIT 8" in sql
        assert params["oid"] == 2

    def test_search_columns_sql_shape(self):
        store = PgvectorSchemaStore(dim=8)
        sql, params = store.search_columns_sql([0.0] * 8, table_id=10, top_k=20)
        assert "<=>" in sql
        assert "core_field" in sql
        assert "table_id" in sql
        assert "LIMIT 20" in sql
        assert params["table_id"] == 10
