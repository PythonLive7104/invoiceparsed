"""Dodo Payments integration.

Two halves:
  - create_checkout(): start a hosted subscription checkout for a plan and return
    the payment link the browser should be sent to.
  - verify_webhook(): validate an incoming Dodo webhook using the Standard
    Webhooks signing scheme (https://www.standardwebhooks.com), then the caller
    applies the plan change.

Everything is gated behind configuration: if DODO_API_KEY isn't set the app runs
in "demo mode" and plan changes are applied instantly without real payment (see
routes/billing_routes.py). This keeps local dev and the demo working unchanged.
"""
import base64
import hashlib
import hmac
import json
import os
import time

import httpx

from config import Config
from plans import get_plan

# Maps our internal plan id → the configured Dodo product/price id.
_PRODUCT_ENV = {
    "starter": "DODO_PRODUCT_STARTER",
    "pro": "DODO_PRODUCT_PRO",
    "business": "DODO_PRODUCT_BUSINESS",
}


def is_configured() -> bool:
    return bool(Config.DODO_API_KEY)


def product_id_for(plan: str) -> str | None:
    import os
    env_key = _PRODUCT_ENV.get(plan)
    return os.getenv(env_key) if env_key else None


class BillingError(Exception):
    """Raised when a checkout cannot be created."""


def create_checkout(user, plan: str, return_url: str) -> str:
    """Create a Dodo subscription checkout and return the hosted payment link.

    We attach the user id and target plan as metadata so the webhook can apply
    the change to the right account after payment succeeds.
    """
    if not is_configured():
        raise BillingError("Dodo Payments is not configured.")
    product_id = product_id_for(plan)
    if not product_id:
        raise BillingError(f"No Dodo product configured for the {plan} plan.")

    payload = {
        "product_id": product_id,
        "quantity": 1,
        "payment_link": True,
        "return_url": return_url,
        "customer": {"email": user.email, "name": user.name or user.email},
        # Dodo requires a billing object; the hosted checkout page collects the
        # real address from the customer. Country is a required placeholder.
        "billing": {
            "city": "",
            "country": os.getenv("DODO_DEFAULT_COUNTRY", "US"),
            "state": "",
            "street": "",
            "zipcode": "",
        },
        "metadata": {"user_id": user.id, "plan": plan},
    }
    try:
        resp = httpx.post(
            f"{Config.DODO_API_BASE.rstrip('/')}/subscriptions",
            headers={
                "Authorization": f"Bearer {Config.DODO_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
    except Exception as exc:  # noqa: BLE001
        raise BillingError(f"Could not reach Dodo Payments: {exc}") from exc

    if not resp.is_success:
        raise BillingError(f"Dodo Payments error {resp.status_code}: {resp.text}")

    data = resp.json()
    link = data.get("payment_link") or data.get("url") or data.get("checkout_url")
    if not link:
        raise BillingError("Dodo Payments did not return a payment link.")
    return link


# ─── Webhook verification (Standard Webhooks) ────────────────────────────────
def _secret_key() -> bytes:
    secret = Config.DODO_WEBHOOK_SECRET
    if secret.startswith("whsec_"):
        secret = secret[len("whsec_"):]
    # Standard Webhooks secrets are base64-encoded.
    try:
        return base64.b64decode(secret)
    except Exception:
        return secret.encode("utf-8")


def _sign(msg_id: str, timestamp: str, body: bytes) -> str:
    signed = f"{msg_id}.{timestamp}.".encode("utf-8") + body
    digest = hmac.new(_secret_key(), signed, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_webhook(headers, raw_body: bytes, *, tolerance: int = 300) -> dict:
    """Verify a Dodo webhook and return the parsed JSON event.

    Raises ValueError if the signature/timestamp is missing or invalid.
    `headers` is any case-insensitive mapping (e.g. flask request.headers).
    """
    if not Config.DODO_WEBHOOK_SECRET:
        raise ValueError("DODO_WEBHOOK_SECRET is not configured.")

    msg_id = headers.get("webhook-id")
    timestamp = headers.get("webhook-timestamp")
    signature = headers.get("webhook-signature")
    if not (msg_id and timestamp and signature):
        raise ValueError("Missing webhook signature headers.")

    # Reject stale/replayed messages.
    try:
        if abs(time.time() - int(timestamp)) > tolerance:
            raise ValueError("Webhook timestamp outside tolerance.")
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid webhook timestamp.") from exc

    expected = _sign(msg_id, timestamp, raw_body)
    # The header may carry several space-separated "v1,<sig>" entries.
    candidates = [part.split(",", 1)[-1] for part in signature.split(" ") if part]
    if not any(hmac.compare_digest(expected, cand) for cand in candidates):
        raise ValueError("Webhook signature mismatch.")

    try:
        return json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid webhook body.") from exc


def plan_from_event(event: dict) -> tuple[str | None, str | None]:
    """Pull (user_id, plan) out of a verified webhook event's metadata.

    Looks in the common locations Dodo nests data/metadata under.
    """
    data = event.get("data") or event
    meta = data.get("metadata") or (data.get("subscription") or {}).get("metadata") or {}
    user_id = meta.get("user_id")
    plan = meta.get("plan")
    if plan and plan not in ("free",) and get_plan(plan)["id"] != plan:
        plan = None  # unknown plan id
    return user_id, plan
