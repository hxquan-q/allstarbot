"""Production adapters that assemble a :class:`SqlAgent` from real pieces.

* :func:`make_llm_generate` / :func:`make_llm_repair` wrap the modular prompt
  builder (``apps.chat.prompts``) + any langchain chat model, and parse the
  model's JSON output back to a SQL string.
* :func:`make_executor` wraps ``apps.db.db.exec_sql(ds, sql)`` (the safety
  gate still runs inside the agent's execute node before this is called).

With these, ``SqlAgent(llm_generate=make_llm_generate(llm),
llm_repair=make_llm_repair(llm), executor=make_executor(exec_sql, ds))`` is a
production-ready generate→execute→repair agent. Tested with
``FakeListChatModel`` + a fake executor.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from apps.chat.prompts import SqlPromptInput, build_sql_messages
from apps.db.safety import get_sql_dialect_name

_FENCE_RE = re.compile(r"^\s*```(?:json|sql)?\s*(.*?)\s*```\s*$", re.IGNORECASE | re.DOTALL)
_ROLE_TO_MESSAGE = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}


def extract_sql_from_llm_output(content) -> str:
    """Pull a SQL string out of an LLM response.

    Handles JSON ``{"sql": "..."}`` (with or without a markdown fence) and
    falls back to the raw text. The agent's safety gate validates the result
    before execution regardless.
    """
    text = getattr(content, "content", content)
    text = str(text).strip()

    fence = _FENCE_RE.match(text)
    if fence:
        text = fence.group(1).strip()

    try:
        payload = json.loads(text)
    except Exception:
        return text

    if isinstance(payload, dict):
        for key in ("sql", "sql_query", "query"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return text


def _to_langchain_messages(msg_dicts: list):
    return [_ROLE_TO_MESSAGE[m["role"]](m["content"]) for m in msg_dicts]


def make_llm_generate(llm) -> Callable:
    """Return ``generate(question, schema_context, ds_type) -> sql``."""

    def generate(question: str, schema_context: str, ds_type: str) -> str:
        dialect = get_sql_dialect_name(ds_type) if ds_type else "SQL"
        messages = build_sql_messages(
            SqlPromptInput(dialect=dialect, schema_context=schema_context, question=question)
        )
        ai = llm.invoke(_to_langchain_messages(messages))
        return extract_sql_from_llm_output(ai)

    return generate


def make_llm_repair(llm) -> Callable:
    """Return ``repair(sql, error, schema_context, ds_type) -> sql``."""

    def repair(sql: str, error: str, schema_context: str, ds_type: str) -> str:
        dialect = get_sql_dialect_name(ds_type) if ds_type else "SQL"
        question = (
            f"The following {dialect} SQL failed to execute:\n\n{sql}\n\n"
            f"Database error:\n{error}\n\n"
            f"Rewrite it into a single correct read-only query that preserves the "
            f"original intent."
        )
        messages = build_sql_messages(
            SqlPromptInput(dialect=dialect, schema_context=schema_context, question=question)
        )
        ai = llm.invoke(_to_langchain_messages(messages))
        return extract_sql_from_llm_output(ai)

    return repair


def make_executor(exec_sql_fn, ds) -> Callable:
    """Return ``executor(sql) -> rows`` wrapping ``exec_sql_fn(ds, sql)``."""

    def executor(sql: str):
        return exec_sql_fn(ds, sql)

    return executor
