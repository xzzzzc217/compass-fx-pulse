"""HTTP entry point for the Function Calling Agent.

GET /api/agent?query=...&trace=1
    SSE stream. `trace=1` includes intermediate tool-call traces (for debug
    panels); omit for plain chat-style output.

POST /api/agent/tools
    Returns the registered tool schemas (for an "Agent capabilities" UI panel).
"""
from flask import Blueprint, Response, jsonify, request, stream_with_context

from .agent.core import stream_agent
from .agent.tools import TOOLS

bp = Blueprint("agent", __name__)


@bp.route("/api/agent", methods=["GET", "POST"])
def agent():
    user_text = request.args.get("query") or (request.json or {}).get("query")
    if not user_text:
        return jsonify({"error": "缺少参数 query"}), 400
    trace = request.args.get("trace") in ("1", "true", "yes")
    return Response(
        stream_with_context(stream_agent(user_text, emit_trace=trace)),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.get("/api/agent/tools")
def list_tools():
    """Expose the tool schemas the agent has access to."""
    return jsonify({
        "n_tools": len(TOOLS),
        "tools": [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "parameters": t["function"]["parameters"],
            }
            for t in TOOLS
        ],
    })
