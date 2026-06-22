import re
from typing import Optional

from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import PromptTemplate


_SQL_FENCE_PATTERN = re.compile(r"^\s*```(?:sql)?\s*(.*?)\s*```\s*$", re.IGNORECASE | re.DOTALL)
_DIALECT_NAMES = {
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

SQL_CHECK_TEMPLATE = """
{query}
Double check the {dialect} query above for common mistakes, including:
- Using NOT IN with NULL values
- Using UNION when UNION ALL should have been used
- Using BETWEEN for exclusive ranges
- Data type mismatch in predicates
- Properly quoting identifiers
- Using the correct number of arguments for functions
- Casting to the correct data type
- Using the proper columns for joins
- Selecting unnecessary columns when only a subset is needed
- Missing a row limit when the user did not request all rows

If there are any mistakes, rewrite the query. If there are no mistakes, reproduce the original query.

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
- Keep the query read-only.
- Use only tables and columns that appear in the schema context.
- Preserve the database dialect and identifier quoting style.
- If the error is about missing/ambiguous columns, prefer explicit table aliases.
- If the error is about identifier quoting, quote the affected identifiers.

Schema context:
{schema}

SQL Query:
"""


def get_sql_dialect_name(ds_type: str) -> str:
    return _DIALECT_NAMES.get((ds_type or "").lower(), ds_type or "SQL")


def clean_sql_checker_output(output: object, fallback: str = "") -> str:
    sql = getattr(output, "content", output)
    if isinstance(sql, list):
        sql = "".join(str(item) for item in sql)
    sql = str(sql or "").strip()

    match = _SQL_FENCE_PATTERN.match(sql)
    if match:
        sql = match.group(1).strip()

    if sql.lower().startswith("sql query:"):
        sql = sql.split(":", 1)[1].strip()

    return sql or fallback


def check_sql_with_langchain(
    llm: BaseLanguageModel,
    sql: str,
    ds_type: str,
) -> str:
    prompt = PromptTemplate.from_template(SQL_CHECK_TEMPLATE)
    chain = prompt | llm
    checked = chain.invoke({"query": sql, "dialect": get_sql_dialect_name(ds_type)})
    return clean_sql_checker_output(checked, fallback=sql)


def repair_sql_with_langchain(
    llm: BaseLanguageModel,
    sql: str,
    ds_type: str,
    error: str,
    schema: Optional[str] = None,
) -> str:
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
    return clean_sql_checker_output(repaired, fallback=sql)
