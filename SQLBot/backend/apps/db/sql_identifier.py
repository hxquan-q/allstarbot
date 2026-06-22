import re
from typing import Iterable


_SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "JOIN", "LEFT", "RIGHT", "FULL", "INNER", "OUTER",
    "ON", "AS", "AND", "OR", "NOT", "IN", "BETWEEN", "LIKE", "IS", "NULL",
    "ORDER", "BY", "GROUP", "HAVING", "LIMIT", "OFFSET", "FETCH", "FIRST",
    "ROWS", "ONLY", "WITH", "UNION", "ALL", "DISTINCT", "CASE", "WHEN", "THEN",
    "ELSE", "END", "ASC", "DESC", "COUNT", "SUM", "AVG", "MAX", "MIN",
}

_QUOTE_PAIRS = {
    "mysql": ("`", "`"),
    "doris": ("`", "`"),
    "starrocks": ("`", "`"),
    "hive": ("`", "`"),
    "sqlserver": ("[", "]"),
}

_TABLE_PREFIX_PATTERN = (
    r"(?P<prefix>\b(?i:FROM|JOIN|UPDATE|INTO|TABLE)\s+"
    r"(?P<schema>(?:[A-Za-z_][\w$]*|`[^`]+`|\"[^\"]+\"|\[[^\]]+\])\.)?)"
)


def _split_sql_literals(sql: str) -> list[tuple[str, bool]]:
    """Split SQL into literal and non-literal parts to avoid replacing inside strings."""
    parts: list[tuple[str, bool]] = []
    start = 0
    i = 0
    while i < len(sql):
        quote = sql[i]
        if quote not in ("'", '"'):
            i += 1
            continue

        if start < i:
            parts.append((sql[start:i], False))

        literal_start = i
        i += 1
        while i < len(sql):
            if sql[i] == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    i += 2
                    continue
                i += 1
                break
            i += 1
        parts.append((sql[literal_start:i], True))
        start = i

    if start < len(sql):
        parts.append((sql[start:], False))
    return parts


def _quote_pair(db_type: str) -> tuple[str, str]:
    return _QUOTE_PAIRS.get((db_type or "").lower(), ('"', '"'))


def _is_quoted(identifier: str, prefix: str, suffix: str) -> bool:
    return identifier.startswith(prefix) and identifier.endswith(suffix)


def _needs_quoting(identifier: str) -> bool:
    if not identifier or identifier.upper() in _SQL_KEYWORDS:
        return False
    return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", identifier) is None


def _quote_identifier(identifier: str, prefix: str, suffix: str) -> str:
    if _is_quoted(identifier, prefix, suffix):
        return identifier
    escaped = identifier.replace(suffix, suffix * 2)
    return f"{prefix}{escaped}{suffix}"


def _normalize_identifier(identifier: str) -> str:
    identifier = identifier.strip()
    if (
        (identifier.startswith('"') and identifier.endswith('"'))
        or (identifier.startswith("`") and identifier.endswith("`"))
        or (identifier.startswith("[") and identifier.endswith("]"))
    ):
        return identifier[1:-1]
    return identifier


def quote_known_table_identifiers(sql: str, table_names: Iterable[str], db_type: str) -> tuple[str, bool]:
    """Quote known table names that require delimiters before SQL execution.

    The function is deliberately narrow: it only rewrites table references after
    SQL table-introducing keywords and only when the unquoted name exists in the
    provided schema-derived table list.
    """
    known_tables = {name for name in table_names if name}
    if not sql or not known_tables:
        return sql, False

    prefix, suffix = _quote_pair(db_type)
    modified = False
    rewritten_parts: list[str] = []

    def replace_table(part: str, table_name: str) -> str:
        nonlocal modified

        pattern = re.compile(
            _TABLE_PREFIX_PATTERN
            + rf"(?P<table>{re.escape(table_name)})(?P<after>(?=\s|,|\)|;|$))"
        )

        def replace_match(match: re.Match) -> str:
            nonlocal modified
            table_token = match.group("table")
            if _is_quoted(table_token, prefix, suffix):
                return match.group(0)

            modified = True
            return f"{match.group('prefix')}{_quote_identifier(table_name, prefix, suffix)}"

        return pattern.sub(replace_match, part)

    for part, is_literal in _split_sql_literals(sql):
        if is_literal:
            rewritten_parts.append(part)
            continue

        for table_name in sorted(known_tables, key=len, reverse=True):
            if _needs_quoting(_normalize_identifier(table_name)):
                part = replace_table(part, table_name)
        rewritten_parts.append(part)

    return "".join(rewritten_parts), modified
