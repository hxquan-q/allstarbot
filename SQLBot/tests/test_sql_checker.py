import os
import sys

from langchain_core.language_models.fake_chat_models import FakeListChatModel


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from apps.db.sql_checker import (  # noqa: E402
    check_sql_with_langchain,
    clean_sql_checker_output,
    ensure_read_only_sql,
    get_sql_dialect_name,
    get_read_only_violation,
    is_read_only_sql,
    repair_sql_with_langchain,
)


def test_clean_sql_checker_output_removes_markdown_fence():
    assert clean_sql_checker_output("```sql\nSELECT id FROM users\n```") == "SELECT id FROM users"


def test_clean_sql_checker_output_removes_sql_query_prefix():
    assert clean_sql_checker_output("SQL Query: SELECT id FROM users") == "SELECT id FROM users"


def test_clean_sql_checker_output_falls_back_when_empty():
    assert clean_sql_checker_output("", fallback="SELECT 1") == "SELECT 1"


def test_clean_sql_checker_output_extracts_sql_from_explanation():
    output = "Here is the fixed query:\n```sql\nSELECT id FROM users LIMIT 5;\n```"

    assert clean_sql_checker_output(output) == "SELECT id FROM users LIMIT 5"


def test_clean_sql_checker_output_extracts_sql_from_tag():
    assert clean_sql_checker_output("<sql>\nSELECT id FROM users\n</sql>") == "SELECT id FROM users"


def test_clean_sql_checker_output_extracts_sql_from_json():
    assert clean_sql_checker_output('{"sql_query":"SELECT id FROM users"}') == "SELECT id FROM users"


def test_clean_sql_checker_output_drops_trailing_explanation_after_sql():
    output = "SELECT id FROM users;\nExplanation: fixed the column name"

    assert clean_sql_checker_output(output) == "SELECT id FROM users"


def test_get_sql_dialect_name_maps_sqlbot_types():
    assert get_sql_dialect_name("pg") == "PostgreSQL"
    assert get_sql_dialect_name("sqlServer") == "Microsoft SQL Server"
    assert get_sql_dialect_name("mysql") == "MySQL"


def test_read_only_validator_accepts_select_and_with():
    assert is_read_only_sql("SELECT id FROM users", "pg") is True
    assert is_read_only_sql("WITH active_users AS (SELECT id FROM users) SELECT id FROM active_users", "pg") is True


def test_read_only_validator_rejects_write_sql():
    violation = get_read_only_violation("DELETE FROM users WHERE id = 1", "pg")

    assert violation
    assert "DELETE" in violation


def test_read_only_validator_ignores_keywords_inside_literals():
    sql = "SELECT 'DELETE FROM users' AS sample FROM audit_log"

    assert is_read_only_sql(sql, "pg") is True


def test_ensure_read_only_sql_raises_for_multiple_statements():
    try:
        ensure_read_only_sql("SELECT id FROM users; DROP TABLE users", "pg")
    except ValueError as exc:
        assert "DROP" in str(exc) or "one statement" in str(exc)
    else:
        raise AssertionError("Expected unsafe SQL to raise")


def test_check_sql_with_langchain_returns_clean_sql():
    llm = FakeListChatModel(responses=["```sql\nSELECT name FROM users LIMIT 5\n```"])

    result = check_sql_with_langchain(llm, "SELECT * FROM users", "pg")

    assert result == "SELECT name FROM users LIMIT 5"


def test_check_sql_with_langchain_keeps_original_if_checker_returns_write_sql():
    llm = FakeListChatModel(responses=["DROP TABLE users"])

    result = check_sql_with_langchain(llm, "SELECT id FROM users", "pg")

    assert result == "SELECT id FROM users"


def test_repair_sql_with_langchain_returns_clean_sql():
    llm = FakeListChatModel(responses=["SQL Query: SELECT name FROM users LIMIT 5"])

    result = repair_sql_with_langchain(
        llm,
        "SELECT bad_column FROM users",
        "mysql",
        "Unknown column 'bad_column'",
        "# Table: users\n[(name:varchar)]",
    )

    assert result == "SELECT name FROM users LIMIT 5"


def test_repair_sql_with_langchain_keeps_original_if_repair_returns_write_sql():
    llm = FakeListChatModel(responses=["UPDATE users SET name = 'x'"])

    result = repair_sql_with_langchain(
        llm,
        "SELECT bad_column FROM users",
        "mysql",
        "Unknown column 'bad_column'",
        "# Table: users\n[(name:varchar)]",
    )

    assert result == "SELECT bad_column FROM users"
