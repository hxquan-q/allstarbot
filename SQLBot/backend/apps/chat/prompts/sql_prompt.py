"""Modular, deduplicated SQL-generation prompt builder.

Replaces the verbose, self-contradictory ``templates/template.yaml`` SQL block
(which repeated the "identifier preservation" rule 3+ times and bundled
chart/multi-dim concerns into the SQL prompt) with a single focused builder.

Production rules are distilled from QueryWeaver's AnalysisAgent P1–P13 rubric
plus the best of the existing template. The builder is a pure function over a
structured input → deterministic ``[system, user]`` messages, so it is
snapshot-tested and ready to wire into the Phase 2 agent (``describe_schema`` →
this prompt → ``query_database``).

NOT swapped into the live pipeline yet (``template.yaml`` still drives
``run_task``); the swap is Phase 2. See design doc §3C.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Production rules — each stated exactly once (dedup invariant).
# --------------------------------------------------------------------------- #
SQL_PRODUCTION_RULES = [
    "Preserve the exact identifiers (table and column names) from the schema, "
    "including their quoting and case.",
    "Emit a single read-only query: SELECT or WITH only. Never "
    "INSERT/UPDATE/DELETE/CREATE/DROP/ALTER/TRUNCATE.",
    "Use only tables and columns present in the provided schema; do not invent "
    "tables, columns, or functions.",
    "Prefer the smallest correct query: join only the tables needed and select "
    "only the columns needed.",
    "Handle NULLs deliberately: choose COUNT(column) vs COUNT(*) with intent, "
    "and guard NOT IN against NULLs (prefer NOT EXISTS or COALESCE).",
    "Use UNION ALL instead of UNION unless you must remove duplicates.",
    "Match the target dialect's functions, identifier quoting, and type casts.",
    "Preserve the user's business intent: filters, grouping, ordering, and any "
    "row limit.",
]

_SYSTEM_PREAMBLE = (
    "You are a senior text-to-SQL engineer. Given a question and the database "
    "schema, write one correct, read-only SQL query.\n\n"
    "The schema is given in M-Schema form: each table is\n"
    "  # Table: <name>, <comment>\n"
    "  [(<column>: <type>, <comment>), ...]\n"
    "Treat every identifier exactly as written."
)

_OUTPUT_FORMAT = (
    "Return ONLY a JSON object with this exact shape:\n"
    "{\n"
    '  "sql": "<the SQL query>",\n'
    '  "tables": ["<table>", ...],\n'
    '  "explanation": "<one short sentence>"\n'
    "}\n"
    "Do not include Markdown fences or any text outside the JSON."
)


def _format_rules() -> str:
    return "Rules:\n" + "\n".join(f"- {rule}" for rule in SQL_PRODUCTION_RULES)


@dataclass
class SqlPromptInput:
    dialect: str
    schema_context: str
    question: str
    examples: list = field(default_factory=list)
    terminology: list = field(default_factory=list)
    history: list = field(default_factory=list)


def build_sql_messages(inp: SqlPromptInput) -> list:
    """Build deterministic ``[system, user]`` chat messages for SQL generation."""
    system = "\n\n".join([_SYSTEM_PREAMBLE, _format_rules(), _OUTPUT_FORMAT])

    user_parts = [
        f"Database dialect: {inp.dialect}",
        f"Schema:\n{inp.schema_context}",
    ]
    if inp.terminology:
        user_parts.append(
            "Business terminology:\n" + "\n".join(f"- {t}" for t in inp.terminology)
        )
    if inp.examples:
        user_parts.append("Examples:\n" + "\n\n".join(inp.examples))
    if inp.history:
        user_parts.append("Previous turns:\n" + "\n".join(inp.history))
    user_parts.append(f"Question: {inp.question}\n\nWrite the SQL query.")

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
