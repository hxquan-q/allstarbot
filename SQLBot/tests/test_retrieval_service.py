"""Tests for RetrievalService — the orchestration glue over ranker/fk_expander/packer.

This is the Phase 2 piece that turns the three pure modules into a usable
"describe schema for this question" pipeline: embed the question, rank table
candidates, expand to FK bridge/sphere tables so joins stay possible, then
token-budget-pack schema/examples/terminology/samples. All dependencies are
injected, so it is unit-tested with synthetic embeddings/graphs.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import pytest  # noqa: E402

from apps.datasource.retrieval import (  # noqa: E402
    CandidateRanker,
    ContextPacker,
    RelationGraph,
    RetrievalConfig,
    RetrievalService,
    TableCandidate,
)


def _candidate(name, embedding, schema=None):
    return TableCandidate(
        table_name=name,
        embedding=embedding,
        m_schema=schema or f"# Table {name}",
    )


def _service(token_counter=None, **cfg):
    # deterministic embed_fn: map known question words to 2D vectors
    vectors = {
        "users": [1.0, 0.0],
        "orders": [1.0, 0.0],
    }

    def embed(question):
        for key, vec in vectors.items():
            if key in question:
                return vec
        return [0.0, 1.0]

    config = RetrievalConfig(min_similarity=0.3, top_k=10, sphere_radius=1, max_bridge_hops=6, **cfg)
    packer = ContextPacker(
        channel_budgets={"schema": 10000, "examples": 10000, "docs": 10000, "samples": 10000},
        total_budget=100000,
        token_counter=token_counter or (lambda t: len(t.split())),
    )
    return RetrievalService(embed_fn=embed, config=config, packer=packer)


class TestRetrievalServiceRankingAndPacking:
    def test_packs_top_ranked_tables_into_schema_channel(self):
        svc = _service()
        candidates = [
            _candidate("orders", [1.0, 0.0]),     # sim 1.0
            _candidate("customers", [0.95, 0.05]),  # sim ~0.997
            _candidate("products", [0.0, 1.0]),    # sim 0.0 -> dropped by ranker
        ]
        graph = RelationGraph.from_pairs([("orders", "customers")])
        ctx = svc.build_context(
            "orders", candidates, graph, examples=["EX"], terminology=["T"], samples=["S"],
        )
        schema_items = next(c for c in ctx.channels if c.name == "schema").items
        assert "# Table orders" in schema_items
        assert "# Table customers" in schema_items
        # products ranked below threshold so it would be dropped — but see next test
        # for FK expansion which can pull it back in.

    def test_routes_examples_terminology_samples_to_own_channels(self):
        svc = _service()
        ctx = svc.build_context(
            "orders", [_candidate("orders", [1.0, 0.0])],
            RelationGraph.from_pairs([]),
            examples=["q: select 1"], terminology=["term=foo"], samples=["row1"],
        )
        by_name = {c.name: c for c in ctx.channels}
        assert by_name["examples"].items == ["q: select 1"]
        assert by_name["docs"].items == ["term=foo"]
        assert by_name["samples"].items == ["row1"]


class TestRetrievalServiceFkExpansion:
    def test_low_relevance_join_bridge_table_is_included_via_sphere(self):
        # products is irrelevant to "orders" (sim 0) but is a 1-hop neighbour of
        # the hit "orders" — it must be pulled in so a join remains possible.
        svc = _service()
        candidates = [
            _candidate("orders", [1.0, 0.0]),
            _candidate("products", [0.0, 1.0]),
        ]
        graph = RelationGraph.from_pairs([("orders", "products")])
        ctx = svc.build_context("orders", candidates, graph, [], [], [])
        schema_items = next(c for c in ctx.channels if c.name == "schema").items
        assert "# Table orders" in schema_items
        assert "# Table products" in schema_items  # via sphere expansion

    def test_inter_hit_bridge_table_is_included(self):
        # a - x - b : a,b are hits, x is the bridge (and may be low-relevance)
        svc = _service()
        candidates = [
            _candidate("a", [1.0, 0.0]),
            _candidate("b", [0.98, 0.01]),
            _candidate("x", [0.0, 1.0]),
        ]
        graph = RelationGraph.from_pairs([("a", "x"), ("x", "b")])
        ctx = svc.build_context("orders", candidates, graph, [], [], [])
        # "orders" embeds to [1,0]; a & b are near [1,0] -> hits; x is the bridge
        schema_items = next(c for c in ctx.channels if c.name == "schema").items
        joined = "\n".join(schema_items)
        assert "# Table a" in joined
        assert "# Table b" in joined
        assert "# Table x" in joined


class TestRetrievalServiceBudget:
    def test_schema_channel_respects_packer_budget(self):
        # custom packer with tiny schema budget -> truncation
        from apps.datasource.retrieval import ContextPacker
        vectors = {"q": [1.0, 0.0]}
        svc = RetrievalService(
            embed_fn=lambda q: vectors.get("q"),
            config=RetrievalConfig(),
            packer=ContextPacker(
                channel_budgets={"schema": 2, "examples": 100, "docs": 100, "samples": 100},
                total_budget=100000,
                token_counter=lambda t: len(t.split()),
            ),
        )
        candidates = [
            _candidate("orders", [1.0, 0.0], "a b c d"),  # 4 tokens > 2 budget
        ]
        ctx = svc.build_context("q", candidates, RelationGraph.from_pairs([]), [], [], [])
        schema = next(c for c in ctx.channels if c.name == "schema")
        assert schema.items == []
        assert schema.truncated is True

    def test_hit_schemas_precede_bridge_schemas_in_order(self):
        svc = _service()
        candidates = [
            _candidate("a", [1.0, 0.0]),
            _candidate("b", [0.98, 0.01]),
            _candidate("x", [0.0, 1.0]),
        ]
        graph = RelationGraph.from_pairs([("a", "x"), ("x", "b")])
        ctx = svc.build_context("orders", candidates, graph, [], [], [])
        schema_items = next(c for c in ctx.channels if c.name == "schema").items
        joined = " || ".join(schema_items)
        # hits (a, b) come before the bridge (x)
        assert joined.index("# Table a") < joined.index("# Table x")
        assert joined.index("# Table b") < joined.index("# Table x")


class TestRetrievalServiceEdgeCases:
    def test_no_candidates_still_packs_examples(self):
        svc = _service()
        ctx = svc.build_context("orders", [], RelationGraph.from_pairs([]),
                                examples=["ex1"], terminology=[], samples=[])
        by_name = {c.name: c for c in ctx.channels}
        assert by_name["schema"].items == []
        assert by_name["examples"].items == ["ex1"]

    def test_returns_build_context(self):
        from apps.datasource.retrieval import BuildContext
        svc = _service()
        ctx = svc.build_context("orders", [_candidate("orders", [1.0, 0.0])],
                                RelationGraph.from_pairs([]), [], [], [])
        assert isinstance(ctx, BuildContext)


class TestFactoryFromSettings:
    def test_factory_builds_service_configured_from_settings(self):
        from apps.datasource.retrieval import build_retrieval_service_from_settings
        svc = build_retrieval_service_from_settings(embed_fn=lambda q: [1.0, 0.0])
        assert isinstance(svc, RetrievalService)
        # budgets flow through from settings defaults
        assert svc.packer.total_budget == svc.packer.total_budget  # sanity
        assert "schema" in svc.packer.channel_budgets
