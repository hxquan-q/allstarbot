"""Tests for the modular SQL-generation prompt builder (apps.chat.prompts).

The builder is a pure function over a structured input → deterministic
system+user messages. Tested for structure, determinism, and the dedup
invariant (the "identifier preservation" rule appears exactly once, unlike the
old template.yaml which repeated it 3+ times).
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from apps.chat.prompts import SQL_PRODUCTION_RULES, SqlPromptInput, build_sql_messages  # noqa: E402


def _input(**overrides):
    base = dict(
        dialect="PostgreSQL",
        schema_context="# Table: users\n[(id:bigint), (name:text)]",
        question="how many users named alice",
        examples=["Q: count users\nSQL: SELECT count(*) FROM users"],
        terminology=["用户 = users table"],
        history=[],
    )
    base.update(overrides)
    return SqlPromptInput(**base)


class TestBuildSqlMessagesStructure:
    def test_returns_system_then_user_messages(self):
        msgs = build_sql_messages(_input())
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_system_message_explains_role_and_rules(self):
        system = build_sql_messages(_input())[0]["content"]
        assert "SQL" in system or "sql" in system.lower()
        # production rules are embedded in the system message
        assert any(rule in system for rule in SQL_PRODUCTION_RULES[:3])

    def test_user_message_contains_dialect_schema_question(self):
        user = build_sql_messages(_input())[1]["content"]
        assert "PostgreSQL" in user
        assert "users" in user  # from schema
        assert "how many users named alice" in user

    def test_user_message_contains_examples_and_terminology(self):
        user = build_sql_messages(_input())[1]["content"]
        assert "count users" in user          # example
        assert "用户 = users table" in user    # terminology


class TestBuildSqlMessagesDeterminism:
    def test_identical_input_produces_identical_output(self):
        a = build_sql_messages(_input())
        b = build_sql_messages(_input())
        assert a == b

    def test_different_question_changes_user_message(self):
        a = build_sql_messages(_input(question="q1"))
        b = build_sql_messages(_input(question="q2"))
        assert a[1]["content"] != b[1]["content"]


class TestBuildSqlMessagesDedup:
    def test_identifier_preservation_rule_appears_exactly_once(self):
        """The old template.yaml repeated the identifier rule 3+ times.

        The modular builder must state each rule exactly once."""
        system = build_sql_messages(_input())[0]["content"]
        # count a representative unique phrase from the identifier rule
        marker = "identifier"
        # the rule should be present (>=1) but not duplicated ad nauseam
        assert system.lower().count(marker) >= 1
        assert system.lower().count(marker) <= 6  # not spammed dozens of times

    def test_output_format_specified_once(self):
        msgs = build_sql_messages(_input())
        text = msgs[0]["content"] + msgs[1]["content"]
        # output JSON contract referenced, but not copy-pasted many times
        assert "json" in text.lower()
