"""Tests for the LangGraph SQL agent core (apps.chat.agent).

The agent's LLM and SQL-executor are injected, so the graph is exercised
end-to-end with fakes — no live database, no real LLM. This proves the
generate → validate → execute → observe → repair (healer) loop and its
termination conditions.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import pytest  # noqa: E402

from apps.chat.agent import AgentResult, SqlAgent  # noqa: E402


def _scripted(responses):
    """Return a callable that returns successive responses from a list."""
    queue = list(responses)

    def _call(*args, **kwargs):
        return queue.pop(0)

    return _call


def _executor_that_fails_on(bad_sqls):
    """Return an executor that raises for any SQL in bad_sqls, else returns rows."""

    def _exec(sql):
        if sql in bad_sqls:
            raise RuntimeError(f"exec failed for {sql}")
        return {"fields": ["x"], "data": [{"x": 1}]}

    return _exec


class TestSqlAgentHappyPath:
    def test_first_try_success(self):
        agent = SqlAgent(
            llm_generate=_scripted(["SELECT 1"]),
            llm_repair=_scripted([]),
            executor=_executor_that_fails_on(set()),
        )
        result = agent.run("how many users", "schema: users(id)", ds_type="pg")
        assert result.status == "ok"
        assert result.sql == "SELECT 1"
        assert result.result == {"fields": ["x"], "data": [{"x": 1}]}
        assert result.error is None
        assert result.attempts == 1

    def test_result_returned_to_caller(self):
        agent = SqlAgent(
            llm_generate=_scripted(["SELECT count(*) FROM t"]),
            llm_repair=_scripted([]),
            executor=lambda sql: {"fields": ["c"], "data": [{"c": 42}]},
        )
        result = agent.run("q", "ctx", "pg")
        assert result.result["data"][0]["c"] == 42


class TestSqlAgentRepairLoop:
    def test_one_repair_then_success(self):
        agent = SqlAgent(
            llm_generate=_scripted(["BAD_SQL"]),         # fails
            llm_repair=_scripted(["SELECT 1"]),          # fixed
            executor=_executor_that_fails_on({"BAD_SQL"}),
            max_attempts=2,
        )
        result = agent.run("q", "ctx", "pg")
        assert result.status == "ok"
        assert result.sql == "SELECT 1"
        assert result.attempts == 2  # 1 generate + 1 repair

    def test_exhausts_retries_and_gives_up(self):
        agent = SqlAgent(
            llm_generate=_scripted(["BAD_1"]),
            llm_repair=_scripted(["BAD_2"]),             # repair also fails
            executor=_executor_that_fails_on({"BAD_1", "BAD_2"}),
            max_attempts=2,
        )
        result = agent.run("q", "ctx", "pg")
        assert result.status == "error"
        assert result.result is None
        assert result.attempts == 2
        assert result.error is not None

    def test_max_attempts_controls_retry_budget(self):
        # max_attempts=3 → two repairs allowed. Use SELECT-shaped SQL so the
        # safety gate passes and the executor is what discriminates ok/fail.
        agent = SqlAgent(
            llm_generate=_scripted(["SELECT bad_a"]),
            llm_repair=_scripted(["SELECT bad_b", "SELECT 1"]),
            executor=_executor_that_fails_on({"SELECT bad_a", "SELECT bad_b"}),
            max_attempts=3,
        )
        result = agent.run("q", "ctx", "pg")
        assert result.status == "ok"
        assert result.sql == "SELECT 1"
        assert result.attempts == 3


class TestSqlAgentSafetyIntegration:
    def test_unsafe_sql_routes_to_repair(self):
        # The generated SQL is a write op; the safety layer (ensure_read_only_sql)
        # rejects it, so the agent must treat it like an execution error and repair.
        agent = SqlAgent(
            llm_generate=_scripted(["DROP TABLE users"]),
            llm_repair=_scripted(["SELECT 1"]),
            executor=_executor_that_fails_on(set()),
            max_attempts=2,
        )
        result = agent.run("q", "ctx", "pg")
        assert result.status == "ok"
        assert result.sql == "SELECT 1"

    def test_persistent_unsafe_sql_gives_up(self):
        agent = SqlAgent(
            llm_generate=_scripted(["DELETE FROM t"]),
            llm_repair=_scripted(["UPDATE t SET x=1"]),  # still unsafe
            executor=lambda sql: {"fields": [], "data": []},
            max_attempts=2,
        )
        result = agent.run("q", "ctx", "pg")
        assert result.status == "error"


class TestSqlAgentContract:
    def test_returns_agent_result_dataclass(self):
        agent = SqlAgent(
            llm_generate=_scripted(["SELECT 1"]),
            llm_repair=_scripted([]),
            executor=lambda sql: {"fields": [], "data": []},
        )
        assert isinstance(agent.run("q", "ctx", "pg"), AgentResult)

    def test_executor_receives_generated_sql(self):
        seen = []
        agent = SqlAgent(
            llm_generate=_scripted(["SELECT 7"]),
            llm_repair=_scripted([]),
            executor=lambda sql: seen.append(sql) or {"fields": [], "data": []},
        )
        agent.run("q", "ctx", "pg")
        assert seen == ["SELECT 7"]

    def test_llm_generate_receives_question_schema_dialect(self):
        captured = {}
        def gen(question, schema_context, ds_type):
            captured.update(question=question, schema=schema_context, ds=ds_type)
            return "SELECT 1"
        agent = SqlAgent(llm_generate=gen, llm_repair=_scripted([]),
                         executor=lambda sql: {"fields": [], "data": []})
        agent.run("how many", "ctx-here", "mysql")
        assert captured == {"question": "how many", "schema": "ctx-here", "ds": "mysql"}
