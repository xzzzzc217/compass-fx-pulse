"""LangGraph state-machine version of the Agent.

This is a parallel implementation of the Function Calling Agent using
LangGraph's StateGraph primitive. It demonstrates the explicit
Plan → Execute → Synthesize → Reflect → (retry / END) pattern as a
visualizable directed graph.

Why have BOTH this and core.py:
  - core.py is the live production path serving /api/agent — battle-tested,
    optimised for streaming UX, has all the latency / error-handling polish.
  - graph.py is the architectural reference — clean state transitions, easy
    to extend, can be exported to PNG via LangGraph's .get_graph() API.
    Useful for documentation, interviews, and future expansions (e.g. adding
    a Critic, a Memory node, parallel ToolExecutor branches).

Run a single query:
    python -m app.agent.graph "什么是 carry trade?"

Visualise the graph:
    python -m app.agent.graph --print-graph
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from ..config import settings
from ..llm import get_agent_client
from .tools import TOOLS, execute


# ============================================================================
# State
# ============================================================================

class AgentState(TypedDict, total=False):
    """Shared state across all nodes. Every node returns a partial dict that
    gets merged into the running state.
    """
    # Inputs (set once at start)
    user_query: str

    # Conversation evolution
    messages: list[dict]

    # Latest LLM decision (consumed by executor or synth)
    pending_tool_calls: list[dict]   # [{id, name, arguments}]

    # Synthesis output
    draft_answer: str

    # Reflection output
    reflection: Optional[dict]       # {score, issues, suggestion}

    # Loop control
    tool_round: int
    retry_count: int

    # Final
    final_answer: str


# ============================================================================
# Constants
# ============================================================================

MAX_TOOL_ROUNDS = 2
MAX_RETRIES = 1
PASS_SCORE = 7

SYSTEM_PROMPT = (
    "你是 CompassFXPulse 智能金融助手。"
    "对于具体数值/统计量类问题调用数据查询工具；对于概念/政策类问题调用 search_forex_knowledge；"
    "其他问题直接回答，不要冗余调用。"
)

REFLECTOR_PROMPT = (
    "你是质量审查员。给定用户问题、工具结果、助手回答，评估并按以下严格 JSON 输出："
    '{"score": 1-10, "issues": "...", "suggestion": "..."} 7 分以上认为可接受。'
)


# ============================================================================
# Nodes
# ============================================================================

def planner_node(state: AgentState) -> dict:
    """Call LLM with tools. Decide whether to call tools or produce content."""
    client = get_agent_client()
    messages = state.get("messages") or [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": state["user_query"]},
    ]

    resp = client.chat.completions.create(
        model=settings.LLM_AGENT_MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.1,
        max_tokens=settings.LLM_MAX_TOKENS,
    )
    msg = resp.choices[0].message

    if msg.tool_calls:
        # Echo assistant's tool_calls into history; executor will append tool results
        messages = messages + [{
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name,
                              "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        }]
        pending = [
            {"id": tc.id, "name": tc.function.name,
             "arguments": tc.function.arguments}
            for tc in msg.tool_calls
        ]
        return {
            "messages": messages,
            "pending_tool_calls": pending,
            "tool_round": state.get("tool_round", 0) + 1,
        }

    # No tool calls — model wants to answer directly
    messages = messages + [{"role": "assistant", "content": msg.content or ""}]
    return {
        "messages": messages,
        "pending_tool_calls": [],
        "draft_answer": msg.content or "",
    }


def executor_node(state: AgentState) -> dict:
    """Execute the tool_calls produced by planner."""
    new_messages = list(state["messages"])
    for tc in state.get("pending_tool_calls", []):
        try:
            args = json.loads(tc["arguments"]) if tc["arguments"] else {}
        except json.JSONDecodeError:
            args = {}
        result = execute(tc["name"], args)
        new_messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "name": tc["name"],
            "content": json.dumps(result, ensure_ascii=False),
        })
    return {"messages": new_messages, "pending_tool_calls": []}


def synthesizer_node(state: AgentState) -> dict:
    """Produce a draft answer from the accumulated messages."""
    if state.get("draft_answer"):
        return {}  # planner already filled it in (no tools needed)

    client = get_agent_client()
    base_msgs = state["messages"]

    # If we're in a retry, append the reflection notes as a steering hint
    if state.get("retry_count", 0) > 0 and state.get("reflection"):
        ref = state["reflection"]
        base_msgs = base_msgs + [{
            "role": "system",
            "content": (f"上一版回答 score={ref.get('score')}，问题：{ref.get('issues')}；"
                        f"建议：{ref.get('suggestion')}。请改进。"),
        }]

    resp = client.chat.completions.create(
        model=settings.LLM_AGENT_MODEL,
        messages=base_msgs,
        temperature=0.7,
        max_tokens=settings.LLM_MAX_TOKENS,
    )
    return {"draft_answer": resp.choices[0].message.content or ""}


def reflector_node(state: AgentState) -> dict:
    """Critic LLM rates the draft. Returns reflection dict + bumped retry."""
    client = get_agent_client()
    tool_summaries: list[str] = []
    for m in state["messages"]:
        if m.get("role") == "tool":
            tool_summaries.append(f"[{m.get('name', '?')}] {m.get('content', '')[:200]}")
    tool_block = "\n".join(tool_summaries) or "（无工具调用）"

    user = (
        f"用户问题：{state['user_query']}\n\n"
        f"工具结果：\n{tool_block}\n\n"
        f"草稿回答：\n{state['draft_answer']}"
    )
    try:
        resp = client.chat.completions.create(
            model=settings.LLM_AGENT_MODEL,
            messages=[
                {"role": "system", "content": REFLECTOR_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        obj = json.loads(resp.choices[0].message.content or "{}")
        score = int(max(1, min(10, obj.get("score", 10))))
        return {
            "reflection": {
                "score": score,
                "issues": str(obj.get("issues", "")),
                "suggestion": str(obj.get("suggestion", "")),
            },
            "retry_count": state.get("retry_count", 0) + 1,
        }
    except Exception:
        # Reflector failure → don't block the user
        return {
            "reflection": {"score": 10, "issues": "", "suggestion": ""},
            "retry_count": state.get("retry_count", 0) + 1,
        }


def finalize_node(state: AgentState) -> dict:
    """Set final_answer = draft_answer."""
    return {"final_answer": state.get("draft_answer", "")}


# ============================================================================
# Routing
# ============================================================================

def route_after_planner(state: AgentState) -> str:
    if state.get("pending_tool_calls"):
        return "executor"
    return "synthesizer"


def route_after_executor(state: AgentState) -> str:
    # After tools run, go back to planner — but cap rounds to prevent loops
    if state.get("tool_round", 0) >= MAX_TOOL_ROUNDS:
        return "synthesizer"
    return "planner"


def route_after_reflector(state: AgentState) -> str:
    ref = state.get("reflection") or {}
    if ref.get("score", 10) >= PASS_SCORE:
        return "finalize"
    if state.get("retry_count", 0) > MAX_RETRIES:
        return "finalize"
    return "synthesizer"  # retry synthesis with reflection notes


# ============================================================================
# Build graph
# ============================================================================

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("planner", planner_node)
    g.add_node("executor", executor_node)
    g.add_node("synthesizer", synthesizer_node)
    g.add_node("reflector", reflector_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", route_after_planner,
                            {"executor": "executor", "synthesizer": "synthesizer"})
    g.add_conditional_edges("executor", route_after_executor,
                            {"planner": "planner", "synthesizer": "synthesizer"})
    g.add_edge("synthesizer", "reflector")
    g.add_conditional_edges("reflector", route_after_reflector,
                            {"finalize": "finalize", "synthesizer": "synthesizer"})
    g.add_edge("finalize", END)

    return g.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run(user_query: str) -> AgentState:
    """Single-shot invocation. Returns the terminal state."""
    return get_graph().invoke({
        "user_query": user_query,
        "tool_round": 0,
        "retry_count": 0,
    })


# ============================================================================
# CLI
# ============================================================================

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("query", nargs="?", default=None)
    p.add_argument("--print-graph", action="store_true",
                   help="Print the graph structure (mermaid) and exit")
    args = p.parse_args()

    if args.print_graph:
        graph = get_graph()
        print(graph.get_graph().draw_mermaid())
        return

    if not args.query:
        print("usage: python -m app.agent.graph 'your question'")
        sys.exit(1)

    print(f"Query: {args.query}\n")
    result = run(args.query)
    print(f"Tool rounds: {result.get('tool_round')}")
    print(f"Retries:     {result.get('retry_count')}")
    print(f"Reflection:  {result.get('reflection')}")
    print(f"\n=== Final answer ===\n{result.get('final_answer')}")


if __name__ == "__main__":
    main()
