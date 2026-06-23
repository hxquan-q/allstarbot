"""LLM-driven SQL checker / repair, backed by the unified safety layer.

The read-only enforcement, dialect mapping and literal/comment stripping now
live in :mod:`apps.db.safety` (single source of truth — formerly duplicated
here and in ``apps/db/db.py``). This module keeps the public API used by the
chat pipeline and the tests, and adds the two LangChain steps that sit on top
of the safety layer:

* :func:`check_sql_with_langchain` – ask the model to fix common SQL mistakes;
* :func:`repair_sql_with_langchain` – ask the model to fix an execution error.

Both fall back to the original SQL whenever the model's reply is not itself a
read-only query, so the safety layer is never weakened.
"""
import re
from typing import Optional

from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import PromptTemplate

from apps.db import safety
from apps.db.safety import (  # noqa: F401  (re-exported for back-compat)
    SqlSafetyError,
    ensure_read_only_sql,
    get_read_only_violation,
    get_sql_dialect_name,
    is_read_only_sql,
    strip_sql_semantics,
)

# Back-compat aliases ---------------------------------------------------------
_SQLGLOT_DIALECTS = safety._SQLGLOT_DIALECTS
_DIALECT_NAMES = safety._DIALECT_NAMES


def get_sqlglot_dialect_name(ds_type: str) -> Optional[str]:
    """Back-compat alias for :func:`safety.get_sqlglot_dialect`."""
    return safety.get_sqlglot_dialect(ds_type)


# --------------------------------------------------------------------------- #
# Prompt templates
# --------------------------------------------------------------------------- #
SQL_CHECK_TEMPLATE = """
{query}
You are a SQL query checker, not a SQL agent. Double check the {dialect} query above for common mistakes, including:
- Using NOT IN with NULL values
- Using UNION when UNION ALL should have been used
- Using BETWEEN for exclusive ranges
- Data type mismatch in predicates
- Properly quoting identifiers
- Using the correct number of arguments for functions
- Casting to the correct data type
- Using the proper columns for joins

Rules:
- If there are any mistakes, rewrite the query with the smallest possible change.
- If there are no mistakes, reproduce the original query exactly.
- Keep the query read-only. Only SELECT or WITH queries are allowed.
- Preserve the user's business intent, selected aliases, filters, grouping, ordering, and row limit.
- Do not add new tables, columns, filters, joins, or limits that are not already implied by the query.
- Preserve the database dialect and identifier quoting style.

Output the final SQL query only. Do not include Markdown fences, comments, explanations, or JSON.

SQL Query:
"""

SQL_REPAIR_TEMPLATE = """
The following {dialect} SQL query failed during execution:

<sql>
{query}
</sql>

The database returned this error:

<error>
{error}
</error>

Rewrite the SQL so it can execute successfully while preserving the user's original intent.

Rules:
- Output the final SQL query only.
- Do not include Markdown fences, comments, explanations, or JSON.
- Keep the query read-only. Only SELECT or WITH queries are allowed.
- Fix only the execution error. Do not rewrite unrelated query logic.
- Use only tables and columns that appear in the schema context.
- Preserve the database dialect and identifier quoting style.
- Preserve selected aliases, filters, grouping, ordering, and row limit unless the error requires changing them.
- If the error is about missing/ambiguous columns, prefer explicit table aliases.
- If the error is about identifier quoting, quote the affected identifiers.

Schema context:
{schema}

SQL Query:
"""


# --------------------------------------------------------------------------- #
# Output cleaning (extract a single SQL statement from model output)
# --------------------------------------------------------------------------- #
_SQL_FENCE_PATTERN = re.compile(r"^\s*```(?:sql)?\s*(.*?)\s*```\s*$", re.IGNORECASE | re.DOTALL)
_ANY_FENCE_PATTERN = re.compile(r"```(?:sql|json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)
_SQL_TAG_PATTERN = re.compile(r"<sql>\s*(.*?)\s*</sql>", re.IGNORECASE | re.DOTALL)
_SQL_PREFIX_PATTERN = re.compile(
    r"^\s*(?:sql\s+query|final\s+sql|corrected\s+sql|query)\s*:\s*",
    re.IGNORECASE,
)
_READ_START_PATTERN = re.compile(r"\b(?:SELECT|WITH)\b", re.IGNORECASE)


def _content_to_text(output: object) -> str:
    sql = getattr(output, "content", output)
    if isinstance(sql, list):
        chunks = []
        for item in sql:
            if isinstance(item, dict):
                chunks.append(str(item.get("text") or item.get("content") or ""))
            else:
                chunks.append(str(item))
        return "\n".join(chunk for chunk in chunks if chunk)
    return str(sql or "")


def _extract_json_sql(text: str) -> Optional[str]:
    try:
        import json

        payload = json.loads(text)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None
    for key in ("sql", "sql_query", "query"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _strip_trailing_semicolon(sql: str) -> str:
    sql = sql.strip()
    while sql.endswith(";"):
        sql = sql[:-1].strip()
    return sql


def _trim_after_first_statement(sql: str) -> str:
    i = 0
    length = len(sql)
    while i < length:
        char = sql[i]
        next_char = sql[i + 1] if i + 1 < length else ""

        if char == "-" and next_char == "-":
            i += 2
            while i < length and sql[i] not in "\r\n":
                i += 1
            continue

        if char == "/" and next_char == "*":
            i += 2
            while i + 1 < length and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i += 2
            continue

        if char in ("'", '"', "`"):
            quote = char
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
            i += 1
            while i < length and sql[i] != "]":
                i += 1
            i += 1
            continue

        if char == ";":
            return sql[:i].strip()

        i += 1

    split_match = re.search(
        r"\n\s*(?:explanation|reason|changes?|notes?|说明|解释|原因|变更)\s*[:：]",
        sql,
        re.IGNORECASE,
    )
    if split_match:
        return sql[:split_match.start()].strip()

    return sql.strip()


def clean_sql_checker_output(output: object, fallback: str = "") -> str:
    sql = _content_to_text(output).strip()

    match = _SQL_FENCE_PATTERN.match(sql)
    if match:
        sql = match.group(1).strip()

    match = _ANY_FENCE_PATTERN.search(sql)
    if match:
        sql = match.group(1).strip()

    match = _SQL_TAG_PATTERN.search(sql)
    if match:
        sql = match.group(1).strip()

    json_sql = _extract_json_sql(sql)
    if json_sql:
        sql = json_sql

    sql = _SQL_PREFIX_PATTERN.sub("", sql).strip()
    if not _READ_START_PATTERN.match(sql):
        match = _READ_START_PATTERN.search(sql)
        if match:
            prefix = sql[:match.start()].strip()
            if prefix.strip("("):
                sql = sql[match.start():].strip()

    sql = _trim_after_first_statement(sql)
    sql = _strip_trailing_semicolon(sql)
    return sql or fallback


# --------------------------------------------------------------------------- #
# LangChain check / repair (sit on top of the safety layer)
# --------------------------------------------------------------------------- #
def _safe_checker_result(original_sql: str, candidate_sql: str, ds_type: str) -> str:
    ensure_read_only_sql(original_sql, ds_type)
    if not candidate_sql:
        return original_sql
    if not is_read_only_sql(candidate_sql, ds_type):
        return original_sql
    return candidate_sql


def check_sql_with_langchain(
    llm: BaseLanguageModel,
    sql: str,
    ds_type: str,
) -> str:
    ensure_read_only_sql(sql, ds_type)
    prompt = PromptTemplate.from_template(SQL_CHECK_TEMPLATE)
    chain = prompt | llm
    checked = chain.invoke({"query": sql, "dialect": get_sql_dialect_name(ds_type)})
    checked_sql = clean_sql_checker_output(checked, fallback=sql)
    return _safe_checker_result(sql, checked_sql, ds_type)


def repair_sql_with_langchain(
    llm: BaseLanguageModel,
    sql: str,
    ds_type: str,
    error: str,
    schema: Optional[str] = None,
) -> str:
    ensure_read_only_sql(sql, ds_type)
    prompt = PromptTemplate.from_template(SQL_REPAIR_TEMPLATE)
    chain = prompt | llm
    repaired = chain.invoke(
        {
            "query": sql,
            "dialect": get_sql_dialect_name(ds_type),
            "error": error,
            "schema": schema or "",
        }
    )
    repaired_sql = clean_sql_checker_output(repaired, fallback=sql)
    return _safe_checker_result(sql, repaired_sql, ds_type)
