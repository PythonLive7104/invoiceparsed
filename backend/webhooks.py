"""Webhook delivery.

On a triggering event (e.g. extraction.completed) we POST a signed JSON payload
to each of the user's active webhook endpoints. Deliveries run in a background
thread so they never block the API response, and are retried with exponential
backoff until a 2xx is received or the attempt budget is exhausted.

Each request includes:
  X-InvoiceParsed-Event:     the event name
  X-InvoiceParsed-Delivery:  a unique id (stable across retries of one event)
  X-InvoiceParsed-Attempt:   1-based attempt number
  X-InvoiceParsed-Signature: sha256=<HMAC-SHA256 of the raw body, keyed by secret>
"""
import hashlib
import hmac
import json
import threading
import time
import uuid
from datetime import datetime

import httpx

from config import Config
from extensions import db
from models import Webhook


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _backoff_delay(attempt: int) -> float:
    """Seconds to wait before retry `attempt` (1-based): base * 2^(attempt-1), capped."""
    return min(Config.WEBHOOK_BACKOFF_CAP, Config.WEBHOOK_BACKOFF_BASE * (2 ** (attempt - 1)))


def _attempt(webhook: Webhook, event: str, body: bytes, delivery_id: str, attempt: int) -> int:
    """One HTTP POST. Returns the HTTP status (0 on connection error)."""
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "InvoiceParsed-Webhook/1.0",
        "X-InvoiceParsed-Event": event,
        "X-InvoiceParsed-Delivery": delivery_id,
        "X-InvoiceParsed-Attempt": str(attempt),
        "X-InvoiceParsed-Signature": f"sha256={sign(webhook.secret, body)}",
    }
    try:
        resp = httpx.post(webhook.url, content=body, headers=headers, timeout=Config.WEBHOOK_TIMEOUT)
        return resp.status_code
    except Exception:
        return 0


def deliver(webhook: Webhook, event: str, data: dict, *, sleep=time.sleep) -> int:
    """Deliver one event to one webhook, retrying with backoff until a 2xx or the
    attempt budget runs out. Returns the final HTTP status (0 on error)."""
    body = json.dumps({"event": event, "data": data}, separators=(",", ":")).encode("utf-8")
    delivery_id = uuid.uuid4().hex
    max_attempts = max(1, Config.WEBHOOK_MAX_ATTEMPTS)

    status = 0
    for attempt in range(1, max_attempts + 1):
        status = _attempt(webhook, event, body, delivery_id, attempt)
        if 200 <= status < 300:
            break
        if attempt < max_attempts:
            sleep(_backoff_delay(attempt))

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
