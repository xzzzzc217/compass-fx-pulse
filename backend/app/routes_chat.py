from datetime import datetime
from flask import Blueprint, Response, jsonify, request, stream_with_context

from .db import get_cursor
from .llm import stream_chat

bp = Blueprint("chat", __name__)


@bp.route("/api/messages", methods=["GET", "POST"])
def messages():
    user_text = request.args.get("query") or (request.json or {}).get("query")
    if not user_text:
        return jsonify({"error": "缺少参数 query"}), 400
    return Response(
        stream_with_context(stream_chat(user_text)),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.post("/api/count")
def receive_count():
    if not request.is_json:
        return jsonify({"msg": "Missing JSON in request"}), 400
    data = request.get_json()
    user_chat = data[-2]
    system_chat = data[-1]
    now = datetime.now()
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO aichat (UserMessage, AIMessage, UserMessageTime, AIMessageTime, RecordID)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_chat["text"], system_chat["text"], now, now, user_chat["chatcount"]),
        )
    return jsonify({"status": "success"}), 200


@bp.get("/api/multiple-messages")
def get_multiple_messages():
    with get_cursor() as cur:
        cur.execute(
            "SELECT UserMessage, AIMessage, RecordID FROM aichat ORDER BY RecordID ASC"
        )
        rows = cur.fetchall()

    conversations: list[list[dict]] = []
    current: list[dict] = []
    for row in rows:
        if row[-1] == 0 and current:
            conversations.append(current)
            current = []
        current.extend([
            {"sender": "用户", "text": row[0]},
            {"sender": "系统", "text": row[1]},
        ])
    if current:
        conversations.append(current)
    return jsonify(conversations)
