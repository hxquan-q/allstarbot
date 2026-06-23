"""LangGraph SQL agent core: generate → validate → execute → repair loop.

A small, inspectable :class:`~langgraph.graph.StateGraph` (rather than an opaque
ReAct agent) so the healer loop and its termination are explicit and unit-
testable with injected fakes. The LLM callables (``llm_generate`` /
``llm_repair``) and the SQL ``executor`` are dependencies: in production they
wrap the prompt builders (§3C) + ``apps.db.db.exec_sql``; in tests they are
fakes. The safety layer (:mod:`apps.db.safety`) gates every candidate SQL
before execution.

NOT wired into the chat pipeline yet — Phase 2 replaces the procedural
``LLMService.run_task`` SQL-gen/execute/repair stages with this graph (behind a
feature flag). See docs/superpowers/specs/2026-06-23-…-design.md §3D.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from apps.db.safety import SqlSafetyError, ensure_read_only_sql


class AgentState(TypedDict, total=False):
    question: str
    schema_context: str
    ds_type: str
    sql: str
    result: Any
    error: Optional[str]
    attempts: int
    max_attempts: int
    status: str  # "ok" | "executing" | "error"


@dataclass
class AgentResult:
    sql: str = ""
    result: Any = None
    error: Optional[str] = None
    status: str = "error"
    attempts: int = 0


class SqlAgent:
    """Generate → execute → repair SQL agent.

    Parameters
    ----------
    llm_generate : Callable[[question, schema_context, ds_type], str]
    llm_repair   : Callable[[sql, error, schema_context, ds_type], str]
    executor     : Callable[[sql], Any]   — returns rows; raises on DB error
    max_attempts : int                     — total execution attempts allowed
    """

    def __init__(
        self,
        *,
        llm_generate: Callable,
        llm_repair: Callable,
        executor: Callable,
        max_attempts: int = 2,
    ):
        self.llm_generate = llm_generate
        self.llm_repair = llm_repair
        self.executor = executor
        self.max_attempts = max_attempts
        self.graph = self._build_graph()

    # -- graph nodes --
    def _generate(self, state: AgentState) -> dict:
        sql = self.llm_generate(state["question"], state["schema_context"], state["ds_type"])
        return {"sql": sql, "attempts": state.get("attempts", 0) + 1, "error": None, "result": None}

    def _execute(self, state: AgentState) -> dict:
        sql = state["sql"]
        try:
            ensure_read_only_sql(sql, state["ds_type"])
            result = self.executor(sql)
            return {"result": result, "error": None, "status": "ok"}
        except SqlSafetyError as exc:
            return {"result": None, "error": f"unsafe SQL: {exc}", "status": "executing"}
        except Exception as exc:  # executor / database error → repairable
            return {"result": None, "error": str(exc), "status": "executing"}

    def _repair(self, state: AgentState) -> dict:
        sql = self.llm_repair(state["sql"], state["error"], state["schema_context"], state["ds_type"])
        return {"sql": sql, "attempts": state["attempts"] + 1}

    def _fail(self, state: AgentState) -> dict:
        return {"status": "error"}

    # -- routing --
    def _route(self, state: AgentState) -> str:
        if state.get("status") == "ok":
            return "done"
        if state.get("attempts", 0) >= state.get("max_attempts", self.max_attempts):
            return "give_up"
        return "repair"

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("generate", self._generate)
        builder.add_node("execute", self._execute)
        builder.add_node("repair", self._repair)
        builder.add_node("fail", self._fail)
        builder.add_edge(START, "generate")
        builder.add_edge("generate", "execute")
        builder.add_conditional_edges(
            "execute", self._route, {"done": END, "repair": "repair", "give_up": "fail"}
        )
        builder.add_edge("repair", "execute")
        builder.add_edge("fail", END)
        return builder.compile()

    def run(self, question: str, schema_context: str, ds_type: str = "") -> AgentResult:
        initial: AgentState = {
            "question": question,
            "schema_context": schema_context,
            "ds_type": ds_type,
            "sql": "",
            "result": None,
            "error": None,
            "attempts": 0,
            "max_attempts": self.max_attempts,
            "status": "error",
        }
        final = self.graph.invoke(initial)
        return AgentResult(
            sql=final.get("sql", ""),
            result=final.get("result"),
            error=final.get("error"),
            status=final.get("status", "error"),
            attempts=final.get("attempts", 0),
        )
