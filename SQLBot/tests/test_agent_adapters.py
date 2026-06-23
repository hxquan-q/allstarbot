"""Tests for agent production adapters (apps.chat.agent.adapters).

The adapters wrap the prompt builder + a langchain LLM (generate/repair) and
the SQL executor, so a SqlAgent can be assembled from real production pieces.
Exercised with FakeListChatModel + a fake executor — no real LLM or database.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import pytest  # noqa: E402

from langchain_core.language_models.fake_chat_models import FakeListChatModel  # noqa: E402

from apps.chat.agent import SqlAgent  # noqa: E402
from apps.chat.agent.adapters import (  # noqa: E402
    extract_sql_from_llm_output,
    make_executor,
    make_llm_generate,
    make_llm_repair,
)


def _llm(*responses):
    return FakeListChatModel(responses=list(responses))


class _RecordingLLM:
    """Wraps a FakeListChatModel and records the messages passed to invoke()."""

    def __init__(self, *responses):
        self._inner = FakeListChatModel(responses=list(responses))
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return self._inner.invoke(messages)


class TestExtractSql:
    def test_parses_json_with_sql_key(self):
        assert extract_sql_from_llm_output('{"sql": "SELECT 1", "tables": []}') == "SELECT 1"

    def test_strips_markdown_fence(self):
        raw = "```json\n{\"sql\": \"SELECT 2\"}\n```"
        assert extract_sql_from_llm_output(raw) == "SELECT 2"

    def test_falls_back_to_raw_select_when_not_json(self):
        assert extract_sql_from_llm_output("SELECT 1 FROM users") == "SELECT 1 FROM users"


class TestMakeLlmGenerate:
    def test_invokes_llm_and_returns_sql(self):
        gen = make_llm_generate(_llm('{"sql": "SELECT count(*) FROM users", "tables": ["users"]}'))
        sql = gen("how many users", "schema: users(id)", "pg")
        assert sql == "SELECT count(*) FROM users"

    def test_question_and_schema_reach_the_prompt(self):
        llm = _RecordingLLM('{"sql": "SELECT 1"}')
        gen = make_llm_generate(llm)
        gen("the question", "the schema", "pg")
        combined = " ".join(m.content for m in llm.calls[-1])
        assert "the question" in combined
        assert "the schema" in combined

    def test_handles_non_json_model_output_gracefully(self):
        gen = make_llm_generate(_llm("SELECT 42"))
        assert gen("q", "ctx", "pg") == "SELECT 42"


class TestMakeLlmRepair:
    def test_invokes_llm_and_returns_repaired_sql(self):
        repair = make_llm_repair(_llm('{"sql": "SELECT 1"}'))
        sql = repair("SELECT BAD", "column not found", "schema ctx", "pg")
        assert sql == "SELECT 1"

    def test_error_and_schema_reach_the_prompt(self):
        llm = _RecordingLLM('{"sql": "SELECT 1"}')
        repair = make_llm_repair(llm)
        repair("SELECT BAD", "the error", "the schema", "pg")
        combined = " ".join(m.content for m in llm.calls[-1])
        assert "SELECT BAD" in combined
        assert "the error" in combined
        assert "the schema" in combined


class TestMakeExecutor:
    def test_calls_exec_fn_with_ds_and_sql(self):
        calls = []
        ds = {"type": "pg"}

        def exec_sql(ds, sql):
            calls.append((ds, sql))
            return {"fields": ["x"], "data": [{"x": 1}]}

        executor = make_executor(exec_sql, ds)
        result = executor("SELECT 1")
        assert calls == [(ds, "SELECT 1")]
        assert result["data"] == [{"x": 1}]

    def test_propagates_execution_errors(self):
        def exec_sql(ds, sql):
            raise RuntimeError("boom")

        executor = make_executor(exec_sql, {})
        with pytest.raises(RuntimeError, match="boom"):
            executor("SELECT 1")


class TestAgentAssembledFromAdapters:
    def test_end_to_end_with_adapters_and_fake_llm(self):
        # generate returns a bad SQL (fails at executor), repair returns good SQL
        llm = _llm('{"sql": "SELECT bad"}', '{"sql": "SELECT 1"}')
        gen = make_llm_generate(llm)
        repair = make_llm_repair(llm)

        def exec_sql(ds, sql):
            if "bad" in sql:
                raise RuntimeError("unknown column")
            return {"fields": ["c"], "data": [{"c": 7}]}

        executor = make_executor(exec_sql, {"type": "pg"})
        agent = SqlAgent(llm_generate=gen, llm_repair=repair, executor=executor, max_attempts=2)
        result = agent.run("how many", "schema", "pg")
        assert result.status == "ok"
        assert result.sql == "SELECT 1"
        assert result.result["data"][0]["c"] == 7
