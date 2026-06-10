"""Support endpoints: the rule-based assistant chat and the contact form."""
import re

from flask import Blueprint, current_app, jsonify, request

import support_kb
from config import Config
from emails import send_contact
from extensions import limiter

support_bp = Blueprint("support", __name__, url_prefix="/api")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@support_bp.post("/chat")
@limiter.limit(lambda: current_app.config["RATELIMIT_CHAT"])
def chat():
    """Answer a product question from the local knowledge base (no AI/cost)."""
    data = request.get_json(silent=True) or {}
    # Accept either {message} or {messages:[...]} (use the latest user message).
    message = data.get("message")
    if not message:
        msgs = data.get("messages") or []
        user_msgs = [m for m in msgs if isinstance(m, dict) and m.get("role") == "user"]
        message = user_msgs[-1].get("content") if user_msgs else ""
    if not isinstance(message, str):
        message = ""

    result = support_kb.answer(message[:1000])
    return jsonify(result)


@support_bp.post("/contact")
@limiter.limit(lambda: current_app.config["RATELIMIT_CONTACT"])
def contact():
    """Email a contact-form submission to the team inbox."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()[:120]
    email = (data.get("email") or "").strip()[:254]
    message = (data.get("message") or "").strip()[:5000]

    if not EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address."}), 400
    if len(message) < 5:
        return jsonify({"error": "Please enter a message."}), 400

    sent = send_contact(name, email, message)
    if not sent:
        return jsonify({"error": "Couldn't send your message right now. Please email invoiceparsed@gmail.com."}), 502
    return jsonify({"success": True})
