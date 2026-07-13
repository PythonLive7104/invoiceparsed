"""Paystack integration.

Three halves:
  - create_checkout(): start a hosted subscription checkout for a plan and return
    the authorization URL the browser should be sent to.
  - verify_transaction(): confirm a transaction by its reference. Paystack sends
    the reference back on the callback URL, so the return page can activate the
    plan immediately instead of waiting on a webhook.
  - verify_webhook(): validate an incoming Paystack webhook (HMAC-SHA512 of the
    raw body, keyed with the secret key), then the caller applies the plan change.

Recurring billing needs a Paystack *plan* (a PLN_ code) per paid tier: passing one
to /transaction/initialize is what makes Paystack store the card and re-charge it
monthly. Rather than have you create those by hand and paste the codes into .env,
plan_code_for() provisions them on first use from plans.py — see "Plan provisioning".

Everything is gated behind configuration: if PAYSTACK_SECRET_KEY isn't set the app
runs in "demo mode" and plan changes are applied instantly without real payment
(see routes/billing_routes.py). This keeps local dev and the demo working unchanged.
"""
import hashlib
import hmac
import json
import logging
import os
import threading
from datetime import datetime
from urllib.parse import quote

import httpx

from config import Config
from plans import PLANS, get_plan

logger = logging.getLogger(__name__)

# The tiers that get charged for, and therefore need a Paystack plan.
PAID_PLANS = tuple(pid for pid, p in PLANS.items() if p["price"] > 0)

# Optional escape hatch: set one of these to pin a tier to an existing Paystack plan
# code (e.g. one created by hand in the dashboard) instead of letting the app
# provision it. Left blank — the normal case — the plan is created on first use.
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


def _api_post(path: str, payload: dict) -> dict:
    """POST to a Paystack path with auth, returning the unwrapped `data` object."""
    try:
        resp = httpx.post(
            f"{Config.PAYSTACK_API_BASE.rstrip('/')}{path}",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
    except Exception as exc:  # noqa: BLE001
        raise BillingError(f"Could not reach Paystack: {exc}") from exc
    return _unwrap(resp)


# ─── Plan provisioning ───────────────────────────────────────────────────────
# plans.py is the source of truth. On first use we list the plans on the Paystack
# account, match ours by name, and create any that are missing or whose price has
# since changed. Existing subscribers keep billing against the plan they signed up
# on (Paystack won't reprice a live subscription), which is why _codes maps every
# plan code we've ever used back to its tier, not just the current one.
_lock = threading.RLock()
_codes: dict[str, str] = {}        # PLN_ code → our plan id (incl. superseded plans)
_current: dict[str, str] = {}      # our plan id → the PLN_ code new checkouts use
_unresolvable: set[str] = set()    # codes we've already failed to map; don't re-fetch
_loaded = False


def reset_plan_cache() -> None:
    """Drop the cached plan codes (tests; also lets a process pick up dashboard edits)."""
    global _loaded
    with _lock:
        _codes.clear()
        _current.clear()
        _unresolvable.clear()
        _loaded = False


def _pinned_code(plan_id: str) -> str:
    env_key = _PLAN_ENV.get(plan_id)
    return (os.getenv(env_key) or "").strip() if env_key else ""


def _plan_name(plan_id: str) -> str:
    return f"{Config.PAYSTACK_PLAN_PREFIX} {get_plan(plan_id)['name']}".strip()


def _amount_for(plan_id: str) -> int:
    # Paystack takes the smallest currency unit (cents / kobo).
    return int(get_plan(plan_id)["price"]) * 100


def _is_current(remote: dict, plan_id: str) -> bool:
    """Does this Paystack plan still match what plans.py says the tier costs?"""
    return (
        remote.get("amount") == _amount_for(plan_id)
        and (remote.get("currency") or "").upper() == Config.PAYSTACK_CURRENCY.upper()
        and remote.get("interval") == "monthly"
    )


def _load_plans() -> None:
    """Index the Paystack account's plans by name. Caller holds _lock."""
    global _loaded
    by_name = {_plan_name(pid).lower(): pid for pid in PAID_PLANS}
    for remote in _api_get("/plan?perPage=100") or []:
        plan_id = by_name.get((remote.get("name") or "").strip().lower())
        code = remote.get("plan_code")
        if not plan_id or not code:
            continue  # someone else's plan on this account
        _codes[code] = plan_id
        if _is_current(remote, plan_id):
            _current[plan_id] = code
    _loaded = True


def plan_code_for(plan_id: str) -> str | None:
    """The Paystack plan code new checkouts for this tier should use.

    Creates the plan in Paystack the first time a tier is bought (or the first time
    after its price changed in plans.py). Raises BillingError if Paystack is
    unreachable — the caller turns that into a failed checkout.
    """
    if plan_id not in PAID_PLANS:
        return None
    pinned = _pinned_code(plan_id)
    if pinned:
        return pinned

    with _lock:
        if not _loaded:
            _load_plans()
        if plan_id in _current:
            return _current[plan_id]

        data = _api_post("/plan", {
            "name": _plan_name(plan_id),
            "amount": _amount_for(plan_id),
            "interval": "monthly",
            "currency": Config.PAYSTACK_CURRENCY,
            "description": get_plan(plan_id)["tagline"],
        })
        code = data.get("plan_code")
        if not code:
            raise BillingError(f"Paystack did not return a plan code for {plan_id}.")
        logger.info(
            "Provisioned Paystack plan %s (%s %s/month) → %s",
            _plan_name(plan_id), Config.PAYSTACK_CURRENCY, get_plan(plan_id)["price"], code,
        )
        _codes[code] = plan_id
        _current[plan_id] = code
        return code


def plan_for_code(code: str | None) -> str | None:
    """Reverse of plan_code_for: our plan id for a Paystack plan code.

    Needed because subscription.* webhooks carry the plan code but no metadata.
    Resolves superseded plans too, so a subscriber still on last year's price maps
    to the right tier. Never raises — an unmappable code just yields None.
    """
    if not code:
        return None
    for plan_id in PAID_PLANS:
        if _pinned_code(plan_id) == code:
            return plan_id

    with _lock:
        if code in _codes:
            return _codes[code]
        if code in _unresolvable:
            return None
        # Unknown: it may be a plan another worker provisioned after we last looked.
        try:
            _load_plans()
        except BillingError as exc:
            logger.warning("Could not list Paystack plans to resolve %s: %s", code, exc)
            return None
        if code in _codes:
            return _codes[code]
        _unresolvable.add(code)
        return None


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
        raise BillingError(f"{plan} is not a paid plan.")

    data = _api_post("/transaction/initialize", {
        "email": user.email,
        "amount": _amount_for(plan),
        "currency": Config.PAYSTACK_CURRENCY,
        "plan": plan_code,
        "callback_url": return_url,
        "metadata": {"user_id": user.id, "plan": plan},
    })
    url = data.get("authorization_url")
    if not url:
        raise BillingError("Paystack did not return a checkout URL.")
    return url


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
