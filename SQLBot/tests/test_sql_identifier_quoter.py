import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from apps.db.sql_identifier import quote_known_table_identifiers  # noqa: E402


def test_quotes_postgres_table_with_dash():
    sql, modified = quote_known_table_identifiers(
        "SELECT * FROM order-items",
        {"order-items"},
        "pg",
    )

    assert modified is True
    assert sql == 'SELECT * FROM "order-items"'


def test_quotes_mysql_table_with_backticks():
    sql, modified = quote_known_table_identifiers(
        "SELECT * FROM order-items",
        {"order-items"},
        "mysql",
    )

    assert modified is True
    assert sql == "SELECT * FROM `order-items`"


def test_quotes_sqlserver_table_with_brackets():
    sql, modified = quote_known_table_identifiers(
        "SELECT * FROM order-items",
        {"order-items"},
        "sqlServer",
    )

    assert modified is True
    assert sql == "SELECT * FROM [order-items]"


def test_quotes_joined_tables_without_touching_aliases():
    sql, modified = quote_known_table_identifiers(
        "SELECT oi.id FROM order-items oi JOIN user accounts ua ON oi.user_id = ua.id",
        {"order-items", "user accounts"},
        "pg",
    )

    assert modified is True
    assert '"order-items" oi' in sql
    assert '"user accounts" ua' in sql
    assert '"oi"' not in sql
    assert '"ua"' not in sql


def test_does_not_modify_unknown_table():
    sql = "SELECT * FROM unknown-table"

    result, modified = quote_known_table_identifiers(sql, {"known-table"}, "pg")

    assert modified is False
    assert result == sql


def test_does_not_modify_normal_identifier():
    sql = "SELECT * FROM users"

    result, modified = quote_known_table_identifiers(sql, {"users"}, "pg")

    assert modified is False
    assert result == sql


def test_does_not_modify_table_name_inside_string_literal():
    sql = "SELECT 'FROM order-items' AS sample FROM order-items"

    result, modified = quote_known_table_identifiers(sql, {"order-items"}, "pg")

    assert modified is True
    assert result == 'SELECT \'FROM order-items\' AS sample FROM "order-items"'


def test_does_not_double_quote_existing_identifier():
    sql = 'SELECT * FROM "order-items"'

    result, modified = quote_known_table_identifiers(sql, {"order-items"}, "pg")

    assert modified is False
    assert result == sql


def test_quotes_schema_qualified_table():
    sql, modified = quote_known_table_identifiers(
        "SELECT * FROM public.order-items",
        {"order-items"},
        "pg",
    )

    assert modified is True
    assert sql == 'SELECT * FROM public."order-items"'
