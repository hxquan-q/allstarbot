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
    get_sql_dialect_name,
    repair_sql_with_langchain,
)


def test_clean_sql_checker_output_removes_markdown_fence():
    assert clean_sql_checker_output("```sql\nSELECT id FROM users\n```") == "SELECT id FROM users"


def test_clean_sql_checker_output_removes_sql_query_prefix():
    assert clean_sql_checker_output("SQL Query: SELECT id FROM users") == "SELECT id FROM users"


def test_clean_sql_checker_output_falls_back_when_empty():
    assert clean_sql_checker_output("", fallback="SELECT 1") == "SELECT 1"


def test_get_sql_dialect_name_maps_sqlbot_types():
    assert get_sql_dialect_name("pg") == "PostgreSQL"
    assert get_sql_dialect_name("sqlServer") == "Microsoft SQL Server"
    assert get_sql_dialect_name("mysql") == "MySQL"


def test_check_sql_with_langchain_returns_clean_sql():
    llm = FakeListChatModel(responses=["```sql\nSELECT name FROM users LIMIT 5\n```"])

    result = check_sql_with_langchain(llm, "SELECT * FROM users", "pg")

    assert result == "SELECT name FROM users LIMIT 5"


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
