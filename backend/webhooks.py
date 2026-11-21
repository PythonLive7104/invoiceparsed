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
import ipaddress
import logging
import socket
import threading
import time
import uuid
from datetime import datetime
from urllib.parse import urlsplit

import httpx

from config import Config
from extensions import db
from json_provider import dumps as json_dumps
from models import Webhook

logger = logging.getLogger(__name__)


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


# ─── SSRF guard ──────────────────────────────────────────────────────────────
# A webhook URL is attacker-supplied and we fetch it from inside the network, so
# without this a customer could aim one at the Postgres container, Redis, or the
# cloud metadata endpoint and read the status code back off the /test endpoint.
class UnsafeWebhookUrl(Exception):
    """Raised when a webhook URL resolves somewhere we refuse to send to."""


def _is_forbidden_ip(ip: ipaddress._BaseAddress) -> bool:
    """True for any address that isn't a normal public destination."""
    # ::ffff:127.0.0.1 and friends: judge the embedded IPv4 address instead.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return _is_forbidden_ip(mapped)
    return (
        ip.is_private        # 10/8, 172.16/12, 192.168/16, fc00::/7 — our own network
        or ip.is_loopback    # 127/8, ::1 — the API itself, the admin panel
        or ip.is_link_local  # 169.254/16 — cloud instance metadata
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def assert_safe_url(url: str) -> None:
    """Raise UnsafeWebhookUrl unless `url` is an http(s) URL whose host resolves
    entirely to public addresses.

    Every resolved address must be public, not just the first: a hostname with
    both a public and a private record would otherwise be a coin flip. Set
    WEBHOOK_ALLOW_PRIVATE_HOSTS=true to switch the check off for local testing.
    """
    if not isinstance(url, str) or len(url) > 2048:
        raise UnsafeWebhookUrl("Enter a valid http(s) URL.")

    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeWebhookUrl("Enter a valid http(s) URL.")
    host = parts.hostname
    if not host:
        raise UnsafeWebhookUrl("Enter a valid http(s) URL.")

    if Config.WEBHOOK_ALLOW_PRIVATE_HOSTS:
        return

    try:
        infos = socket.getaddrinfo(host, parts.port or None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, ValueError) as exc:
        raise UnsafeWebhookUrl(f"Could not resolve '{host}'.") from exc

    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise UnsafeWebhookUrl(f"Could not resolve '{host}'.")

    for raw in addresses:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            raise UnsafeWebhookUrl(f"Could not resolve '{host}'.") from None
        if _is_forbidden_ip(ip):
            raise UnsafeWebhookUrl(
                "That URL points to a private or internal address. "
                "Webhooks must target a publicly reachable host."
            )


def url_is_safe(url: str) -> bool:
    try:
        assert_safe_url(url)
        return True
    except UnsafeWebhookUrl:
        return False


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
    # Re-validate on every attempt, not just at creation: DNS can be re-pointed
    # at a private address after a URL was accepted (rebinding).
    if not url_is_safe(webhook.url):
        logger.warning(
            "webhook %s skipped: %s no longer resolves to a public address",
            webhook.id, webhook.url,
        )
        return 0
    try:
        resp = httpx.post(
            webhook.url,
            content=body,
            headers=headers,
            timeout=Config.WEBHOOK_TIMEOUT,
            # httpx's default, made explicit: following a redirect would hand an
            # attacker a one-hop route past the guard above.
            follow_redirects=False,
        )
        return resp.status_code
    except Exception:
        return 0


def deliver(webhook: Webhook, event: str, data: dict, *, sleep=time.sleep, max_attempts=None) -> int:
    """Deliver one event to one webhook, retrying with backoff until a 2xx or the
    attempt budget runs out. Returns the final HTTP status (0 on error).

    `max_attempts` overrides the configured budget — the manual "test" endpoint
    passes 1 so it doesn't block the request thread on backoff sleeps.
    """
    body = json_dumps({"event": event, "data": data}, separators=(",", ":")).encode("utf-8")
    delivery_id = uuid.uuid4().hex
    if max_attempts is None:
        max_attempts = Config.WEBHOOK_MAX_ATTEMPTS
    max_attempts = max(1, max_attempts)

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


def dispatch(app, organization_id: str, event: str, data: dict) -> None:
    """Fire `event` to an organization's active webhooks, in a background thread.

    Scoped by organization rather than by the uploading user: a webhook belongs
    to the organization, so a document uploaded by one member must still notify
    the endpoints the team configured.
    """
    def run():
        with app.app_context():
            hooks = Webhook.query.filter_by(
                organization_id=organization_id, active=True
            ).all()
            for hook in hooks:
                deliver(hook, event, data)

    threading.Thread(target=run, daemon=True).start()
