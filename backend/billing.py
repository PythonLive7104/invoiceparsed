"""Paystack integration.

Three halves:
  - create_checkout(): start a hosted subscription checkout for a plan and return
    the authorization URL the browser should be sent to.
  - verify_transaction(): confirm a transaction by its reference. Paystack sends
    the reference back on the callback URL, so the return page can activate the
    plan immediately instead of waiting on a webhook.
  - verify_webhook(): validate an incoming Paystack webhook (HMAC-SHA512 of the
    raw body, keyed with the secret key), then the caller applies the plan change.

Everything is gated behind configuration: if PAYSTACK_SECRET_KEY isn't set the app
runs in "demo mode" and plan changes are applied instantly without real payment
(see routes/billing_routes.py). This keeps local dev and the demo working unchanged.
"""
import hashlib
import hmac
import json
import os
from datetime import datetime
from urllib.parse import quote

import httpx

from config import Config
from plans import PLANS, get_plan

# Maps our internal plan id → the env var holding the configured Paystack plan code.
_PLAN_ENV = {
    "starter": "PAYSTACK_PLAN_STARTER",
    "pro": "PAYSTACK_PLAN_PRO",
    "business": "PAYSTACK_PLAN_BUSINESS",
}

# Paystack subscription states that still entitle the user to their plan.
# "non-renewing" means they cancelled but the paid period hasn't ended yet.
_ENTITLING_STATUSES = {"active", "non-renewing"}

# Paystack reports a paid charge as "success"; "succeeded" is accepted so rows
# written by the previous provider still read as paid.
SUCCESS_STATUSES = {"success", "succeeded"}


def is_configured() -> bool:
    return bool(Config.PAYSTACK_SECRET_KEY)


def plan_code_for(plan: str) -> str | None:
    """The Paystack plan code (PLN_…) configured for one of our plan ids."""
    env_key = _PLAN_ENV.get(plan)
    return os.getenv(env_key) if env_key else None


def plan_for_code(code: str | None) -> str | None:
    """Reverse of plan_code_for: our plan id for a Paystack plan code.

    Needed because subscription.* webhooks carry the plan code but no metadata.
    """
    if not code:
        return None
    for plan_id in _PLAN_ENV:
        if plan_code_for(plan_id) == code:
            return plan_id
    return None


class BillingError(Exception):
    """Raised when a checkout or API call cannot be completed."""


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {Config.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


def _unwrap(resp) -> dict:
    """Paystack wraps every response as {status, message, data}. Return `data`."""
    if not resp.is_success:
        raise BillingError(f"Paystack error {resp.status_code}: {resp.text}")
    try:
        body = resp.json()
    except ValueError as exc:
        raise BillingError("Paystack returned a non-JSON response.") from exc
    if not body.get("status"):
        raise BillingError(f"Paystack error: {body.get('message') or 'unknown'}")
    return body.get("data") or {}


def create_checkout(user, plan: str, return_url: str) -> str:
    """Initialize a Paystack transaction and return the hosted checkout URL.

    Passing `plan` makes Paystack create a subscription once the charge succeeds,
    and the plan's own amount/currency take precedence over the `amount` we send.
    We attach the user id and target plan as metadata so both the callback and the
    webhook can apply the change to the right account.
    """
    if not is_configured():
        raise BillingError("Paystack is not configured.")
    plan_code = plan_code_for(plan)
    if not plan_code:
        raise BillingError(f"No Paystack plan configured for the {plan} plan.")

    payload = {
        "email": user.email,
        # Paystack takes the smallest currency unit (cents / kobo).
        "amount": int(get_plan(plan)["price"]) * 100,
        "currency": Config.PAYSTACK_CURRENCY,
        "plan": plan_code,
        "callback_url": return_url,
        "metadata": {"user_id": user.id, "plan": plan},
    }
    try:
        resp = httpx.post(
            f"{Config.PAYSTACK_API_BASE.rstrip('/')}/transaction/initialize",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
    except Exception as exc:  # noqa: BLE001
        raise BillingError(f"Could not reach Paystack: {exc}") from exc

    url = _unwrap(resp).get("authorization_url")
    if not url:
        raise BillingError("Paystack did not return a checkout URL.")
    return url


def _api_get(path: str, *, allow_missing: bool = False) -> dict | None:
    """GET a Paystack path with auth, returning the unwrapped `data` object.

    With allow_missing=True a 404 returns None instead of raising (Paystack 404s
    when a customer has never transacted).
    """
    try:
        resp = httpx.get(
            f"{Config.PAYSTACK_API_BASE.rstrip('/')}{path}",
            headers=_headers(),
            timeout=15,
        )
    except Exception as exc:  # noqa: BLE001
        raise BillingError(f"Could not reach Paystack: {exc}") from exc
    if allow_missing and resp.status_code == 404:
        return None
    return _unwrap(resp)


def verify_transaction(reference: str) -> dict:
    """Fetch a transaction by reference so we can trust its status server-side.

    This is what the post-checkout return page calls: Paystack redirects back with
    ?reference=…, and a verify call tells us authoritatively whether it was paid.
    """
    if not is_configured():
        raise BillingError("Paystack is not configured.")
    return _api_get(f"/transaction/verify/{quote(str(reference), safe='')}") or {}


# ─── Webhook verification ────────────────────────────────────────────────────
def _sign(raw_body: bytes) -> str:
    """Paystack's signature: HMAC-SHA512 of the raw body, keyed with the secret key."""
    return hmac.new(
        Config.PAYSTACK_SECRET_KEY.encode("utf-8"), raw_body, hashlib.sha512
    ).hexdigest()


def verify_webhook(headers, raw_body: bytes) -> dict:
    """Verify a Paystack webhook and return the parsed JSON event.

    Raises ValueError if the signature is missing or invalid. `headers` is any
    case-insensitive mapping (e.g. flask request.headers).
    """
    if not Config.PAYSTACK_SECRET_KEY:
        raise ValueError("PAYSTACK_SECRET_KEY is not configured.")

    signature = headers.get("x-paystack-signature")
    if not signature:
        raise ValueError("Missing webhook signature header.")
    if not hmac.compare_digest(_sign(raw_body), signature):
        raise ValueError("Webhook signature mismatch.")

    try:
        return json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid webhook body.") from exc


# ─── Reading events ──────────────────────────────────────────────────────────
def _metadata(data: dict) -> dict:
    """Paystack echoes metadata back as an object, but sometimes as a JSON string."""
    meta = data.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            return {}
    return meta if isinstance(meta, dict) else {}


def _plan_code_in(data: dict) -> str | None:
    """Dig the plan code out of a payload: `plan` is an object on subscription
    events, a bare code on some charges, and `plan_object` in transaction lists."""
    plan = data.get("plan")
    if isinstance(plan, dict):
        return plan.get("plan_code")
    if isinstance(plan, str) and plan:
        return plan
    return (data.get("plan_object") or {}).get("plan_code")


def plan_from_event(event: dict) -> tuple[str | None, str | None]:
    """Pull (user_id, plan) out of a verified webhook event.

    charge.success carries our checkout metadata. subscription.* events don't, so
    we fall back to resolving the plan from the Paystack plan code (and the caller
    falls back to the customer email for the user — see customer_email_from_event).
    """
    data = event.get("data") or event
    meta = _metadata(data)
    user_id = meta.get("user_id")
    plan = meta.get("plan") or plan_for_code(_plan_code_in(data))
    if plan and plan not in PLANS:
        plan = None  # unknown plan id
    return user_id, plan


def customer_email_from_event(event: dict) -> str | None:
    data = event.get("data") or event
    return (data.get("customer") or {}).get("email")


def payment_from_event(event: dict) -> dict:
    """Pull payment details out of a verified webhook event for recording."""
    data = event.get("data") or event
    return payment_from_transaction(data)


def payment_from_transaction(txn: dict) -> dict:
    """Normalise a Paystack transaction (from a webhook, a verify, or a list)."""
    meta = _metadata(txn)
    return {
        "payment_id": txn.get("reference") or txn.get("id"),
        # Paystack amounts are already in the smallest currency unit.
        "amount": txn.get("amount"),
        "currency": txn.get("currency"),
        "status": txn.get("status"),
        "plan": meta.get("plan") or plan_for_code(_plan_code_in(txn)),
        "subscription_id": txn.get("subscription_code")
        or (txn.get("subscription") or {}).get("subscription_code"),
        "created_at": _parse_dt(txn.get("paid_at") or txn.get("created_at")),
    }


def _parse_dt(value):
    """Parse Paystack's ISO timestamps to a naive UTC datetime, tolerating 'Z'."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


# ─── Reconciliation ──────────────────────────────────────────────────────────
def fetch_customer_billing(user) -> dict:
    """Pull a user's real transactions and active subscription straight from Paystack.

    Used by the "Confirm payment" sync so a paid user can reconcile their account
    even if a webhook was missed. Returns:
        {"payments": [ {payment_id, amount, currency, status, plan,
                        subscription_id, created_at}, ... ],
         "active_plan": <plan id or None>}
    """
    if not is_configured():
        raise BillingError("Paystack is not configured.")

    # Paystack looks customers up by email or customer code on the same route.
    customer = _api_get(f"/customer/{quote(user.email, safe='')}", allow_missing=True)
    if not customer:
        return {"payments": [], "active_plan": None}

    def is_mine(meta: dict) -> bool:
        # The customer is email-bound, but prefer an explicit metadata match.
        uid = (meta or {}).get("user_id")
        return uid is None or uid == user.id

    payments = []
    txns = _api_get(f"/transaction?customer={customer['id']}&perPage=50") or []
    for txn in txns:
        if not is_mine(_metadata(txn)):
            continue
        payments.append(payment_from_transaction(txn))

    # The customer payload embeds their subscriptions, so no second call needed.
    active_plan = None
    for sub in customer.get("subscriptions") or []:
        if sub.get("status") not in _ENTITLING_STATUSES:
            continue
        plan = plan_for_code(_plan_code_in(sub))
        if plan:
            active_plan = plan

    return {"payments": payments, "active_plan": active_plan}
