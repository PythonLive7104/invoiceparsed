"""Webhook delivery.

On a triggering event (e.g. extraction.completed) we POST a signed JSON payload
to each of the user's active webhook endpoints. Deliveries run in a background
thread so they never block the API response.

Each request includes:
  X-InvoiceParsed-Event:     the event name
  X-InvoiceParsed-Signature: sha256=<HMAC-SHA256 of the raw body, keyed by secret>
"""
import hashlib
import hmac
import json
import threading
from datetime import datetime

import httpx

from config import Config
from extensions import db
from models import Webhook


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def deliver(webhook: Webhook, event: str, data: dict) -> int:
    """Deliver one event to one webhook. Returns the HTTP status (0 on error)."""
    body = json.dumps({"event": event, "data": data}, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "InvoiceParsed-Webhook/1.0",
        "X-InvoiceParsed-Event": event,
        "X-InvoiceParsed-Signature": f"sha256={sign(webhook.secret, body)}",
    }
    try:
        resp = httpx.post(webhook.url, content=body, headers=headers, timeout=Config.WEBHOOK_TIMEOUT)
        status = resp.status_code
    except Exception:
        status = 0
    webhook.last_status = status
    webhook.last_delivery_at = datetime.utcnow()
    db.session.commit()
    return status


def dispatch(app, user_id: str, event: str, data: dict) -> None:
    """Fire `event` to all of a user's active webhooks, in a background thread."""
    def run():
        with app.app_context():
            hooks = Webhook.query.filter_by(user_id=user_id, active=True).all()
            for hook in hooks:
                deliver(hook, event, data)

    threading.Thread(target=run, daemon=True).start()
