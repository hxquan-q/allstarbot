"""Unified, AST-first read-only SQL safety layer.

This module is the single source of truth for "is this SQL a safe read-only
query?". It merges the two former implementations (``apps/db/sql_checker.py``
and ``apps/db/db.py:check_sql_read``) into one core with explicit policy
flags, so each call site keeps its original behaviour:

* the SQL-generation validation path (``sql_checker``) is permissive on
  functions and strips comments/literals to avoid false positives;
* the execution-time gate (``db.check_sql_read``) additionally rejects
  "dangerous functions" (``pg_read_file``, ``LOAD_FILE``, ``version()`` …)
  and may allow metadata commands (``SHOW`` / ``DESCRIBE`` / ``EXPLAIN``).

Design goals (see docs/superpowers/specs/2026-06-23-…-design.md):

* depends only on ``sqlglot`` (+ stdlib) so it is unit-testable with no live
  database, no LLM and no app config;
* comments and string literals are stripped before keyword/pattern detection
  so neither ``SELECT 'DELETE'`` (false positive) nor comment-based bypass can
  occur;
* exactly one statement is required — multi-statement SQL is rejected.
"""
from __future__ import annotations

import re
from typing import Optional

import sqlglot
from sqlglot import exp


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class SqlSafetyError(ValueError):
    """Raised when SQL violates the read-only policy (by ensure_read_only_sql)."""


class SqlParseError(SqlSafetyError):
    """Raised when sqlglot cannot parse the SQL and strict_parse is enabled."""


# --------------------------------------------------------------------------- #
# Dialect mapping (union of the two former maps)
# --------------------------------------------------------------------------- #
_SQLGLOT_DIALECTS: dict[str, str] = {
    "ck": "clickhouse",
    "clickhouse": "clickhouse",
    "dm": "oracle",
    "doris": "mysql",
    "excel": "postgres",
    "hive": "hive",
    "kingbase": "postgres",
    "mysql": "mysql",
    "oracle": "oracle",
    "pg": "postgres",
    "postgres": "postgres",
    "postgresql": "postgres",
    "redshift": "redshift",
    "sqlserver": "tsql",
    "starrocks": "mysql",
}

_DIALECT_NAMES: dict[str, str] = {
    "ck": "ClickHouse",
    "dm": "DM",
    "doris": "Doris",
    "es": "Elasticsearch SQL",
    "excel": "PostgreSQL",
    "hive": "Hive",
    "kingbase": "Kingbase",
    "mysql": "MySQL",
    "oracle": "Oracle",
    "pg": "PostgreSQL",
    "redshift": "AWS Redshift",
    "sqlserver": "Microsoft SQL Server",
    "starrocks": "StarRocks",
}

_BASE_READ_COMMANDS = {"SELECT", "WITH"}
_METADATA_COMMANDS = {"SHOW", "DESCRIBE", "DESC", "EXPLAIN"}

_DENIED_WRITE_COMMANDS = {
    "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "TRUNCATE",
    "MERGE", "COPY", "REPLACE", "GRANT", "REVOKE", "CALL", "EXEC", "EXECUTE",
    "USE", "SET",
}

_WRITE_NODE_TYPES = tuple(
    t for t in (
        getattr(exp, "Insert", None),
        getattr(exp, "Update", None),
        getattr(exp, "Delete", None),
        getattr(exp, "Create", None),
        getattr(exp, "Drop", None),
        getattr(exp, "Alter", None),
        getattr(exp, "Merge", None),
        getattr(exp, "Copy", None),
        getattr(exp, "Truncate", None),
    ) if t is not None
)

# Dangerous patterns that the AST node-type check may not capture. Applied to
# the literal/comment-stripped text so they cannot be hidden inside a string
# or comment.
_DANGEROUS_PATTERNS = (
    re.compile(r"\bINTO\s+OUTFILE\b", re.IGNORECASE),
    re.compile(r"\bINTO\s+DUMPFILE\b", re.IGNORECASE),
    re.compile(r"\bLOAD_FILE\s*\(", re.IGNORECASE),
    re.compile(r"\bCOPY\b[\s\S]*?\bTO\s+PROGRAM\b", re.IGNORECASE),
    re.compile(r"\bXP_CMDSHELL\b", re.IGNORECASE),
    re.compile(r"\bSP_EXECUTESQL\b", re.IGNORECASE),
)

# Common information-disclosure functions blocked for every dialect.
_COMMON_DANGEROUS_FUNCTIONS = {"version", "current_user", "user", "database"}

# Vendor-specific dangerous functions (file access / RCE / shell).
_DS_DANGEROUS_FUNCTIONS: dict[str, set[str]] = {
    "mysql": {"LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE"},
    "doris": {"LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE"},
    "starrocks": {"LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE"},
    "pg": {"pg_read_file", "pg_write_file", "lo_import", "lo_export"},
    "postgres": {"pg_read_file", "pg_write_file", "lo_import", "lo_export"},
    "postgresql": {"pg_read_file", "pg_write_file", "lo_import", "lo_export"},
    "sqlserver": {"EXEC", "xp_cmdshell", "sp_executesql"},
    "tsql": {"EXEC", "xp_cmdshell", "sp_executesql"},
    "oracle": {"UTL_FILE", "DBMS_PIPE", "DBMS_LOCK"},
    "hive": {"ADD FILE", "ADD JAR"},
}


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #
def get_sqlglot_dialect(ds_type: str) -> Optional[str]:
    return _SQLGLOT_DIALECTS.get((ds_type or "").lower())


def get_sql_dialect_name(ds_type: str) -> str:
    return _DIALECT_NAMES.get((ds_type or "").lower(), ds_type or "SQL")


def get_dangerous_functions(ds_type: str) -> set[str]:
    functions = set(_COMMON_DANGEROUS_FUNCTIONS)
    ds_key = (ds_type or "").lower()
    functions.update(_DS_DANGEROUS_FUNCTIONS.get(ds_key, ()))
    # also honour canonical sqlglot dialect keys (e.g. caller passes "postgres")
    glot = _SQLGLOT_DIALECTS.get(ds_key)
    if glot:
        functions.update(_DS_DANGEROUS_FUNCTIONS.get(glot, ()))
    return functions


# --------------------------------------------------------------------------- #
# Comment / literal stripping (ported verbatim from the former sql_checker —
# proven correct by test_sql_checker + test_sql_safety).
# --------------------------------------------------------------------------- #
def strip_sql_semantics(sql: str) -> str:
    """Return ``sql`` with comments and string/identifier literals replaced by
    spaces, so keyword/pattern detection cannot be fooled by their contents."""
    chars: list[str] = []
    i = 0
    length = len(sql)

    while i < length:
        char = sql[i]
        next_char = sql[i + 1] if i + 1 < length else ""

        if char == "-" and next_char == "-":
            chars.append(" ")
            i += 2
            while i < length and sql[i] not in "\r\n":
                i += 1
            continue

        if char == "/" and next_char == "*":
            chars.append(" ")
            i += 2
            while i + 1 < length and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i += 2
            continue

        if char in ("'", '"', "`"):
            quote = char
            chars.append(" ")
            i += 1
            while i < length:
                if sql[i] == quote:
                    if i + 1 < length and sql[i + 1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                if quote == "'" and sql[i] == "\\":
                    i += 2
                    continue
                i += 1
            continue

        if char == "[":
            chars.append(" ")
            i += 1
            while i < length and sql[i] != "]":
                i += 1
            i += 1
            continue

        chars.append(char)
        i += 1

    return "".join(chars)


def _strip_trailing_semicolons(sql: str) -> str:
    sql = sql.strip()
    while sql.endswith(";"):
        sql = sql[:-1].strip()
    return sql


# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #
def get_read_only_violation(
    sql: str,
    ds_type: str = "",
    *,
    allow_metadata: bool = False,
    check_dangerous_functions: bool = False,
    strict_parse: bool = False,
) -> Optional[str]:
    """Return a violation reason string, or ``None`` when the SQL is read-only.

    Parameters mirror the two former call sites' policies:

    * ``allow_metadata`` – also permit ``SHOW``/``DESCRIBE``/``EXPLAIN``.
    * ``check_dangerous_functions`` – reject info-disclosure/file/RCE functions
      (the execution-time gate behaviour).
    * ``strict_parse`` – raise :class:`SqlParseError` instead of tolerating
      SQL that sqlglot cannot parse.
    """
    candidate = _strip_trailing_semicolons(sql)
    if not candidate:
        return "SQL query is empty"

    inspectable = strip_sql_semantics(candidate)

    first_word = re.search(r"\b\w+\b", inspectable)
    first_keyword = first_word.group(0).upper() if first_word else ""

    if not first_keyword:
        return "Unable to determine SQL command"
    if first_keyword in _DENIED_WRITE_COMMANDS:
        return f"Write or control operation '{first_keyword}' is not allowed"

    allowed_read = set(_BASE_READ_COMMANDS)
    if allow_metadata:
        allowed_read |= _METADATA_COMMANDS
    if first_keyword not in allowed_read:
        return (
            f"SQL command '{first_keyword}' is not allowed. "
            f"Only read queries are permitted"
        )

    # Dangerous textual patterns (on stripped text → no string/comment hiding).
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(inspectable):
            return f"SQL contains dangerous pattern: {pattern.pattern}"

    # Dangerous functions (vendor file/RCE/info-disclosure). Detected by token
    # scan on the stripped text: a token counts only when it is called — i.e.
    # followed by "(" or "." (schema-qualified) — so a column literally named
    # "user" or "version" never triggers. Stripping guarantees no hiding in a
    # string/comment. This is more robust than walking AST nodes, because
    # sqlglot represents builtins (version, current_user) as non-Anonymous Func
    # nodes and drops schema prefixes (UTL_FILE.GET_LINE → "GET_LINE").
    if check_dangerous_functions:
        token_violation = _find_dangerous_function_token(inspectable, ds_type)
        if token_violation:
            return token_violation

    is_metadata_cmd = first_keyword in _METADATA_COMMANDS

    # Parse for AST-level checks. Vendor metadata commands are notoriously
    # inconsistent to parse, so they rely on the keyword/pattern gate above.
    try:
        statements = sqlglot.parse(candidate, dialect=get_sqlglot_dialect(ds_type))
    except Exception as exc:  # sqlglot does not support every vendor syntax
        if strict_parse:
            raise SqlParseError(str(exc)) from exc
        return None

    statements = [s for s in statements if s is not None]

    if is_metadata_cmd:
        # Best-effort: no reliable AST contract across vendors for metadata.
        return None

    if len(statements) != 1:
        return "SQL must contain exactly one statement"

    statement = statements[0]
    if _WRITE_NODE_TYPES and (
        isinstance(statement, _WRITE_NODE_TYPES)
        or any(statement.find_all(*_WRITE_NODE_TYPES))
    ):
        return f"SQL contains write operation: {type(statement).__name__}"

    has_select = isinstance(statement, exp.Select) or any(statement.find_all(exp.Select))
    if not has_select:
        return f"SQL statement type '{type(statement).__name__}' is not a read query"

    return None


def _find_dangerous_function_token(inspectable: str, ds_type: str) -> Optional[str]:
    """Token-scan the stripped SQL for dangerous function calls.

    A token matches only when called (followed by ``(`` or ``.``), which keeps
    columns with the same name (``user``, ``version``) safe. Space-containing
    tokens (``INTO OUTFILE``, ``ADD FILE``) are ignored here — they are covered
    by the always-on pattern set.
    """
    tokens = {t for t in get_dangerous_functions(ds_type) if " " not in t}
    if not tokens:
        return None
    upper = inspectable.upper()
    for token in tokens:
        pattern = re.compile(r"\b" + re.escape(token.upper()) + r"\s*(?:\(|\.)")
        if pattern.search(upper):
            return f"SQL contains dangerous function: {token}"
    return None


def is_read_only_sql(
    sql: str,
    ds_type: str = "",
    *,
    allow_metadata: bool = False,
    check_dangerous_functions: bool = False,
    strict_parse: bool = False,
) -> bool:
    return get_read_only_violation(
        sql,
        ds_type,
        allow_metadata=allow_metadata,
        check_dangerous_functions=check_dangerous_functions,
        strict_parse=strict_parse,
    ) is None


def ensure_read_only_sql(
    sql: str,
    ds_type: str = "",
    *,
    allow_metadata: bool = False,
    check_dangerous_functions: bool = False,
    strict_parse: bool = False,
) -> str:
    violation = get_read_only_violation(
        sql,
        ds_type,
        allow_metadata=allow_metadata,
        check_dangerous_functions=check_dangerous_functions,
        strict_parse=strict_parse,
    )
    if violation:
        raise SqlSafetyError(violation)
    return sql
