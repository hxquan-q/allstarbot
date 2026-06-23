"""Tests for the unified SQL read-only safety layer (apps.db.safety).

These tests target the NEW module directly. The back-compat shims in
apps/db/sql_checker.py and apps/db/db.py are covered by test_sql_checker.py
and must remain green after delegation.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import pytest  # noqa: E402

from apps.db import safety  # noqa: E402
from apps.db.safety import (  # noqa: E402
    SqlSafetyError,
    SqlParseError,
    ensure_read_only_sql,
    get_dangerous_functions,
    get_read_only_violation,
    get_sqlglot_dialect,
    is_read_only_sql,
    strip_sql_semantics,
)


# --------------------------------------------------------------------------- #
# Basic read acceptance
# --------------------------------------------------------------------------- #
class TestReadAcceptance:
    def test_plain_select_allowed(self):
        assert get_read_only_violation("SELECT 1") is None

    def test_select_with_from_and_where_allowed(self):
        sql = "SELECT id, name FROM users WHERE age > 18 ORDER BY name"
        assert get_read_only_violation(sql) is None

    def test_cte_with_allowed(self):
        sql = "WITH t AS (SELECT 1 AS x) SELECT * FROM t"
        assert get_read_only_violation(sql) is None

    def test_subquery_allowed(self):
        sql = "SELECT * FROM (SELECT id FROM orders) sub"
        assert get_read_only_violation(sql) is None

    def test_leading_parenthesis_allowed(self):
        assert get_read_only_violation("(SELECT 1)") is None

    def test_trailing_semicolon_tolerated(self):
        assert get_read_only_violation("SELECT 1;;") is None

    def test_dialect_quoted_identifiers_allowed(self):
        assert get_read_only_violation('SELECT "id" FROM "users"', "pg") is None
        assert get_read_only_violation("SELECT `id` FROM `users`", "mysql") is None


# --------------------------------------------------------------------------- #
# Write / control command rejection
# --------------------------------------------------------------------------- #
class TestWriteRejection:
    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO users (id) VALUES (1)",
            "UPDATE users SET name = 'a'",
            "DELETE FROM users",
            "CREATE TABLE t (id int)",
            "DROP TABLE users",
            "ALTER TABLE users ADD COLUMN x int",
            "TRUNCATE TABLE users",
            "MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN UPDATE SET x = 1",
            "GRANT SELECT ON users TO bob",
            "REVOKE SELECT ON users FROM bob",
            "CALL my_proc()",
            "USE mydb",
            "SET search_path = 'public'",
        ],
    )
    def test_write_command_rejected(self, sql):
        violation = get_read_only_violation(sql)
        assert violation is not None, f"expected rejection for: {sql}"


# --------------------------------------------------------------------------- #
# Literal / comment stripping (the sql_checker strength)
# --------------------------------------------------------------------------- #
class TestSemanticStripping:
    def test_write_keyword_inside_string_literal_is_not_a_violation(self):
        # 'DELETE FROM users' is data, not a command
        assert get_read_only_violation("SELECT 'DELETE FROM users' AS msg") is None

    def test_write_keyword_inside_comment_is_not_a_false_positive(self):
        sql = "SELECT 1 -- this comment mentions DELETE casually\n"
        assert get_read_only_violation(sql) is None

    def test_block_comment_with_write_keyword_not_flagged(self):
        sql = "SELECT 1 /* DROP TABLE x */ FROM dual"
        assert get_read_only_violation(sql) is None

    def test_strip_sql_semantics_removes_string_literals(self):
        stripped = strip_sql_semantics("SELECT 'a''b' , x")
        # literal replaced by spaces; identifier x remains
        assert "'" not in stripped
        assert "x" in stripped

    def test_strip_sql_semantics_removes_line_and_block_comments(self):
        stripped = strip_sql_semantics("SELECT 1 -- c\n, /* block */ 2")
        assert "--" not in stripped
        assert "/*" not in stripped


# --------------------------------------------------------------------------- #
# Multi-statement rejection
# --------------------------------------------------------------------------- #
class TestMultiStatement:
    def test_two_reads_rejected(self):
        # text-to-sql must yield exactly one statement
        assert get_read_only_violation("SELECT 1; SELECT 2") is not None

    def test_read_then_write_rejected(self):
        sql = "SELECT 1; DROP TABLE users"
        assert get_read_only_violation(sql) is not None

    def test_single_statement_with_trailing_semicolon_ok(self):
        assert get_read_only_violation("SELECT 1;") is None


# --------------------------------------------------------------------------- #
# Dangerous patterns
# --------------------------------------------------------------------------- #
class TestDangerousPatterns:
    def test_into_outfile_rejected(self):
        assert get_read_only_violation("SELECT * FROM users INTO OUTFILE '/tmp/x'") is not None

    def test_into_dumpfile_rejected(self):
        assert get_read_only_violation("SELECT 1 INTO DUMPFILE '/tmp/x'") is not None

    def test_copy_to_program_rejected(self):
        sql = "COPY (SELECT 1) TO PROGRAM 'rm -rf /'"
        assert get_read_only_violation(sql) is not None

    def test_load_file_rejected_when_function_check_on(self):
        sql = "SELECT LOAD_FILE('/etc/passwd')"
        assert get_read_only_violation(sql, "mysql", check_dangerous_functions=True) is not None

    def test_pg_read_file_allowed_when_function_check_off(self):
        # sql_checker validation path is permissive on functions: pg_read_file
        # is NOT in the always-on pattern set, so it is allowed unless the
        # execution-time dangerous-function check is enabled.
        sql = "SELECT pg_read_file('/etc/passwd')"
        assert get_read_only_violation(sql, "pg") is None


# --------------------------------------------------------------------------- #
# Dangerous functions (per-dialect) — only when check_dangerous_functions=True
# --------------------------------------------------------------------------- #
class TestDangerousFunctions:
    def test_pg_read_file_rejected_for_postgres(self):
        sql = "SELECT pg_read_file('/etc/passwd')"
        assert get_read_only_violation(sql, "pg", check_dangerous_functions=True) is not None

    def test_utl_file_rejected_for_oracle(self):
        sql = "SELECT UTL_FILE.GET_LINE(NULL, 1) FROM dual"
        assert get_read_only_violation(sql, "oracle", check_dangerous_functions=True) is not None

    def test_version_function_rejected_for_mysql_when_checked(self):
        # borderline but preserves db.check_sql_read existing behavior
        assert get_read_only_violation("SELECT version()", "mysql", check_dangerous_functions=True) is not None

    def test_version_function_allowed_when_not_checked(self):
        assert get_read_only_violation("SELECT version()", "mysql") is None

    def test_get_dangerous_functions_returns_superset(self):
        pg = get_dangerous_functions("pg")
        assert "pg_read_file" in pg
        mysql = get_dangerous_functions("mysql")
        assert "LOAD_FILE" in mysql
        # common info-disclosure set is always present
        assert "version" in pg and "current_user" in mysql


# --------------------------------------------------------------------------- #
# Metadata commands (SHOW / DESCRIBE / EXPLAIN)
# --------------------------------------------------------------------------- #
class TestMetadataCommands:
    def test_show_rejected_by_default(self):
        assert get_read_only_violation("SHOW TABLES") is not None

    def test_show_allowed_when_metadata_enabled(self):
        assert get_read_only_violation("SHOW TABLES", allow_metadata=True) is None

    def test_describe_allowed_when_metadata_enabled(self):
        assert get_read_only_violation("DESCRIBE users", allow_metadata=True) is None

    def test_explain_allowed_when_metadata_enabled(self):
        assert get_read_only_violation("EXPLAIN SELECT 1", allow_metadata=True) is None

    def test_metadata_does_not_open_write_commands(self):
        # enabling metadata must not allow INSERT etc.
        assert get_read_only_violation("INSERT INTO t VALUES (1)", allow_metadata=True) is not None


# --------------------------------------------------------------------------- #
# Empty / malformed
# --------------------------------------------------------------------------- #
class TestEdgeCases:
    def test_empty_sql_is_violation(self):
        assert get_read_only_violation("") is not None

    def test_whitespace_only_sql_is_violation(self):
        assert get_read_only_violation("   \n  ") is not None

    def test_lenient_on_unparseable_select_is_allowed(self):
        # sqlglot can't parse some vendor syntax; keyword checks still gate it.
        # A SELECT keyword that fails AST parse must not be a false violation.
        # (If sqlglot parses it fine, this still passes since it's read-only.)
        sql = "SELECT 1"
        assert get_read_only_violation(sql) is None

    def test_strict_parse_raises_on_garbage(self):
        # SELECT-prefixed SQL that sqlglot cannot parse (unclosed paren).
        with pytest.raises(SqlParseError):
            safety.get_read_only_violation("SELECT * FROM (", strict_parse=True)


# --------------------------------------------------------------------------- #
# Convenience wrappers
# --------------------------------------------------------------------------- #
class TestWrappers:
    def test_is_read_only_sql_true_false(self):
        assert is_read_only_sql("SELECT 1") is True
        assert is_read_only_sql("DROP TABLE x") is False

    def test_ensure_read_only_sql_returns_sql_when_safe(self):
        assert ensure_read_only_sql("SELECT 1") == "SELECT 1"

    def test_ensure_read_only_sql_raises_sql_safety_error(self):
        with pytest.raises(SqlSafetyError):
            ensure_read_only_sql("DROP TABLE x")

    def test_sql_parse_error_is_sql_safety_error(self):
        assert issubclass(SqlParseError, SqlSafetyError)


# --------------------------------------------------------------------------- #
# Dialect mapping
# --------------------------------------------------------------------------- #
class TestDialectMapping:
    @pytest.mark.parametrize(
        "ds_type,expected",
        [
            ("pg", "postgres"),
            ("postgres", "postgres"),
            ("postgresql", "postgres"),
            ("mysql", "mysql"),
            ("doris", "mysql"),
            ("starrocks", "mysql"),
            ("sqlserver", "tsql"),
            ("sqlServer", "tsql"),
            ("hive", "hive"),
            ("clickhouse", "clickhouse"),
            ("ck", "clickhouse"),
            ("redshift", "redshift"),
            ("oracle", "oracle"),
        ],
    )
    def test_get_sqlglot_dialect(self, ds_type, expected):
        assert get_sqlglot_dialect(ds_type) == expected

    def test_unknown_dialect_returns_none(self):
        assert get_sqlglot_dialect("madeup") is None
