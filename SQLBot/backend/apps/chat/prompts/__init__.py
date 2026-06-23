"""Modular prompt builders for the chat pipeline (Phase 1, not yet wired).

See ``sql_prompt.py``. Phase 2 swaps these into the live pipeline, replacing
the ``templates/template.yaml`` blocks.
"""
from apps.chat.prompts.sql_prompt import (
    SQL_PRODUCTION_RULES,
    SqlPromptInput,
    build_sql_messages,
)
from apps.chat.prompts.analysis_prompt import (
    AnalysisPromptInput,
    build_analysis_messages,
)

__all__ = [
    "SQL_PRODUCTION_RULES",
    "SqlPromptInput",
    "build_sql_messages",
    "AnalysisPromptInput",
    "build_analysis_messages",
]
