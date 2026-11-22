"""Bachs payment provider.

The only payment provider. It replaced Paystack, and four of the differences
changed the code rather than just the credentials - worth knowing if you ever
read the pre-Bachs history:

1. **Webhooks are signed with a separate per-endpoint secret**, not the API key.
   The signature covers ``"{timestamp}.{raw_body}"`` with HMAC-SHA256, and the
   V2 header may carry several ``v1=`` values at once during secret rotation.
2. **Amounts are decimal strings in major units** (``"29.00"``), never minor
   units. Paystack used integer kobo/cents, so nothing here multiplies by 100.
3. **There are no plan objects and no create-subscription endpoint.** A
   subscription only comes into being by completing a checkout that contains a
   recurring product, so a product id stands in for Paystack's ``PLN_`` code.
4. **Renewal invoices are not guaranteed to carry our metadata.** Checkout
   metadata is documented as copied onto the *subscription*; propagation to
   invoices is not documented. So the subscription id is persisted against the
   user when the subscription is first seen, and later invoices are matched on
   that id rather than on metadata that may be absent.

The payload field names are inconsistent across Bachs' own event types — a
subscription id is ``data.subscription_id`` in events but ``id`` on the API
object, a charge is ``charge.id`` in events but ``charge.payment_id`` on the
checkout object, and ``collection.failed`` uses ``data.customer.id`` where the
subscription events use ``data.customer.customer_id``. The readers below accept
every documented spelling rather than betting on one.
"""
import hashlib
import hmac
import json
import logging
import time

import httpx

from config import Config
from money import to_decimal
from plans import PLANS

logger = logging.getLogger(__name__)

PROVIDER = "bachs"

# ─── Events ──────────────────────────────────────────────────────────────────
# Paid access begins. A subscription checkout emits collection.succeeded,
# customer.subscription.created and invoice.paid; whichever arrives first grants,
# and the rest are idempotent no-ops.
ACTIVATING = {
    "checkout.completed",
    "collection.succeeded",
    "customer.subscription.created",
    "invoice.paid",
}

# Paid access ends. Per the subscription lifecycle docs: "remove access when you
# receive customer.subscription.deleted, not when the cancellation is
# scheduled." A cancel-at-period-end only emits customer.subscription.updated
# with cancel_at_period_end=true, and access is meant to continue until the
# period actually ends — so scheduling must NOT revoke.
DEACTIVATING = {"customer.subscription.deleted"}

# Status-driven access, from the lifecycle page's own table. past_due is "your
# choice": access is kept during the retry window, because dunning is expected
# to recover and cutting a paying customer off on a single failed charge is
# worse than a few days of grace. If retries are exhausted, the account setting
# decides between canceled (-> customer.subscription.deleted, revoked) and
# unpaid (-> customer.subscription.updated, revoked here).
ENTITLING_STATUSES = {"trialing", "active", "past_due"}
REVOKING_STATUSES = {"unpaid", "canceled"}
# "paused" appears in the event status enum but not in the list filter, and the
# lifecycle table does not say whether it entitles. Treated as not entitling and
# logged, so it surfaces rather than silently granting access.

SUCCESS_STATUSES = {"SUCCEEDED", "succeeded", "paid", "completed"}


class BachsError(Exception):
    """A Bachs API call could not be completed."""


class WebhookNotConfigured(Exception):
    """We cannot verify a delivery because our own credentials are missing.

    Distinct from a bad signature: the caller must answer 5xx so Bachs retries,
    rather than 4xx, which Bachs does not retry.
    """


def is_configured() -> bool:
    return bool(Config.BACHS_SECRET_KEY)


def product_for(plan_id: str) -> str:
    """The Bachs recurring product id standing in for a plan."""
    product = (Config.BACHS_PRODUCTS or {}).get(plan_id, "")
    if not product:
        raise BachsError(
            f"No Bachs product is configured for the '{plan_id}' plan "
            f"(set BACHS_PRODUCT_{plan_id.upper()})."
        )
    return product


def plan_for_product(product_id: str | None) -> str | None:
    """Reverse lookup: which of our plans a product id belongs to."""
    if not product_id:
        return None
    for plan_id, configured in (Config.BACHS_PRODUCTS or {}).items():
        if configured and configured == product_id:
            return plan_id
    return None


# ─── HTTP ────────────────────────────────────────────────────────────────────
def _headers(idempotency_key: str | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {Config.BACHS_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        # Documented as Idempotency-Key; 2xx responses are cached 24h, and the
        # same key with a different body returns 409 IDEMPOTENCY_CONFLICT.
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _url(path: str) -> str:
    return f"{Config.BACHS_API_BASE.rstrip('/')}{path}"


# Provider error codes we can explain better than the provider does. The raw
# message is still logged; only what the CUSTOMER sees is replaced, because a
# 400 full of provider JSON tells them nothing they can act on.
_FRIENDLY_ERRORS = {
    "ACCOUNT_NOT_ACTIVATED": (
        "Card payments are not switched on for this site yet. Nothing was "
        "charged - please try again shortly."
    ),
    "IDEMPOTENCY_CONFLICT": (
        "That checkout was already started. Refresh the page and try again."
    ),
    "IDEMPOTENCY_IN_PROGRESS": (
        "A checkout is already being created. Give it a moment and try again."
    ),
}


class BachsAccountNotActivated(BachsError):
    """The Bachs account cannot take live payments yet.

    Its own class because it is a configuration state, not a transient fault:
    retrying never helps, and the operator - not the customer - has to act.
    """


def _result(resp) -> dict:
    if not resp.is_success:
        # The full body goes to the log for diagnosis; it is never the message
        # shown to a customer, since it can carry provider internals and echo
        # customer details back out.
        detail = resp.text[:500]
        logger.warning("Bachs API error %s: %s", resp.status_code, detail)

        code = ""
        try:
            body = resp.json()
            code = (body or {}).get("error_code") or (body or {}).get("code") or ""
        except ValueError:
            body = {}

        if code == "ACCOUNT_NOT_ACTIVATED":
            raise BachsAccountNotActivated(_FRIENDLY_ERRORS[code])
        if code in _FRIENDLY_ERRORS:
            raise BachsError(_FRIENDLY_ERRORS[code])
        raise BachsError(
            "We could not start the checkout. Nothing was charged - please try again."
        )
    try:
        return resp.json() or {}
    except ValueError as exc:
        raise BachsError("Bachs returned a non-JSON response.") from exc


def _post(path: str, payload: dict, *, idempotency_key: str | None = None) -> dict:
    try:
        resp = httpx.post(
            _url(path), json=payload, headers=_headers(idempotency_key), timeout=20
        )
    except httpx.HTTPError as exc:
        raise BachsError(f"Could not reach Bachs: {exc}") from exc
    return _result(resp)


def _get(path: str) -> dict:
    try:
        resp = httpx.get(_url(path), headers=_headers(), timeout=20)
    except httpx.HTTPError as exc:
        raise BachsError(f"Could not reach Bachs: {exc}") from exc
    return _result(resp)


def _delete(path: str, payload: dict | None = None) -> dict:
    try:
        resp = httpx.request(
            "DELETE", _url(path), json=payload, headers=_headers(), timeout=20
        )
    except httpx.HTTPError as exc:
        raise BachsError(f"Could not reach Bachs: {exc}") from exc
    return _result(resp)


# ─── Checkout ────────────────────────────────────────────────────────────────
def create_checkout(organization, user, plan: str, return_url: str,
                    cancel_url: str | None = None) -> str:
    """Start a hosted subscription checkout and return the URL for the browser.

    The ORGANISATION id, the acting user and the plan travel in `metadata`,
    which is how the resulting webhook is mapped back. The organization matters
    most: the subscription belongs to the tenant, so a renewal must land on the
    right organization even if the person who bought it has since left.

    `reference` carries the organization id and plan as a second handle, because
    it appears on checkout and collection events.
    """
    if plan not in PLANS or plan == "free":
        raise BachsError(f"'{plan}' is not a paid plan.")

    payload = {
        "product_cart": [{"product_id": product_for(plan), "quantity": 1}],
        # Required for a recurring checkout.
        "customer": {"email": user.email, "name": user.name or user.email},
        "success_url": return_url,
        "metadata": {
            "organization_id": str(organization.id),
            "user_id": str(user.id),
            "plan": plan,
        },
        # Max 128 chars and unique per organisation, including expired checkouts
        # — so it carries the attempt time, not just the ids.
        "reference": f"ip_{organization.id}_{plan}_{int(time.time())}",
    }
    if cancel_url:
        payload["cancel_url"] = cancel_url

    # Keyed on the reference so a retried request cannot open two checkouts.
    data = _post("/v1/checkout-sessions", payload, idempotency_key=payload["reference"])
    url = data.get("checkout_url")
    if not url:
        raise BachsError("Bachs did not return a checkout URL.")
    return url


def retrieve_checkout(checkout_id: str) -> dict:
    """Fetch a checkout session. Bachs appends ?checkout_id= to success_url."""
    return _get(f"/v1/checkout-sessions/{checkout_id}")


def cancel_subscription(subscription_id: str, *, at_period_end: bool = True) -> dict:
    """Cancel a subscription.

    `at_period_end` defaults True — the customer keeps what they paid for until
    the period ends. Note Bachs' own default is the opposite: a DELETE with no
    body cancels IMMEDIATELY, so the flag is always sent explicitly.
    """
    return _delete(
        f"/v1/subscriptions/{subscription_id}",
        {"cancel_at_period_end": bool(at_period_end)},
    )


# ─── Webhook verification ────────────────────────────────────────────────────
def _expected_signature(timestamp: str, raw_body: bytes, secret: str) -> str:
    """HMAC-SHA256 hex of "{timestamp}.{raw_body}"."""
    signed = timestamp.encode("utf-8") + b"." + raw_body
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def _parse_v2(header: str) -> tuple[str | None, list[str]]:
    """Parse "t=<ts>,v1=<sig>[,v1=<sig>]" into (timestamp, [signatures]).

    Several v1 values appear while a signing secret is being rotated, and the
    delivery is valid if any of them matches.
    """
    timestamp = None
    signatures = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t" and value:
            timestamp = value
        elif key == "v1" and value:
            signatures.append(value)
    return timestamp, signatures


def verify_webhook(headers, raw_body: bytes) -> dict:
    """Verify a Bachs delivery and return the parsed event.

    Raises WebhookNotConfigured if our signing secret is missing (the caller
    must answer 5xx so Bachs retries), and ValueError if the delivery itself is
    bad (the caller answers 4xx, which Bachs deliberately does not retry).

    `raw_body` must be the bytes as received. Re-serialising parsed JSON changes
    whitespace and key order and invalidates the signature.
    """
    secret = Config.BACHS_WEBHOOK_SECRET
    if not secret:
        raise WebhookNotConfigured(
            "BACHS_WEBHOOK_SECRET is not set, so webhook deliveries cannot be verified."
        )

    v2 = headers.get("X-Bachs-Signature-V2")
    if v2:
        timestamp, signatures = _parse_v2(v2)
        if not timestamp or not signatures:
            raise ValueError("Malformed X-Bachs-Signature-V2 header.")
    else:
        # Legacy pair. Still sent, per the webhooks docs.
        timestamp = headers.get("X-Bachs-Timestamp")
        legacy = headers.get("X-Bachs-Signature")
        if not timestamp or not legacy:
            raise ValueError("Missing webhook signature headers.")
        signatures = [legacy]

    _assert_fresh(timestamp)

    expected = _expected_signature(timestamp, raw_body, secret)
    # compare_digest on every candidate, and no early return, so a mismatch
    # cannot be distinguished by timing.
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise ValueError("Webhook signature mismatch.")

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid webhook body.") from exc
    if not isinstance(event, dict):
        raise ValueError("Webhook body is not a JSON object.")
    return event


def _assert_fresh(timestamp: str) -> None:
    """Reject a delivery outside the replay window."""
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError):
        raise ValueError("Webhook timestamp is not a Unix time.") from None
    drift = abs(time.time() - sent_at)
    if drift > Config.BACHS_WEBHOOK_TOLERANCE:
        raise ValueError(
            f"Webhook timestamp is {int(drift)}s away from now, outside the "
            f"{Config.BACHS_WEBHOOK_TOLERANCE}s tolerance."
        )


# ─── Reading events ──────────────────────────────────────────────────────────
def event_type(event: dict) -> str:
    return (event or {}).get("type") or ""


def event_id(event: dict) -> str | None:
    """The envelope id (evt_...). Delivery is at-least-once, so dedupe on this."""
    return (event or {}).get("id")


def _data(event: dict) -> dict:
    data = (event or {}).get("data")
    return data if isinstance(data, dict) else {}


def _customer(data: dict) -> dict:
    customer = data.get("customer")
    return customer if isinstance(customer, dict) else {}


def subscription_id_from_event(event: dict) -> str | None:
    """Subscription id, wherever this event type happens to put it.

    Subscription events use `data.subscription_id`; invoice and checkout events
    nest it as `data.subscription.subscription_id`; the API object calls it `id`.
    """
    data = _data(event)
    direct = data.get("subscription_id")
    if isinstance(direct, str) and direct:
        return direct
    nested = data.get("subscription")
    if isinstance(nested, dict):
        for key in ("subscription_id", "id"):
            value = nested.get(key)
            if isinstance(value, str) and value:
                return value
    elif isinstance(nested, str) and nested:
        return nested
    # Some checkout payloads expose it under the charge.
    charge = data.get("charge")
    if isinstance(charge, dict):
        value = charge.get("subscription_id")
        if isinstance(value, str) and value:
            return value
    return None


def customer_id_from_event(event: dict) -> str | None:
    """Bachs customer id. `customer_id` on subscription events, `id` on collection.*."""
    customer = _customer(_data(event))
    for key in ("customer_id", "id"):
        value = customer.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def customer_email_from_event(event: dict) -> str | None:
    """Customer email, used as a fallback when no stored mapping matches."""
    data = _data(event)
    email = _customer(data).get("email")
    if isinstance(email, str) and email:
        return email
    details = data.get("customer_details")
    if isinstance(details, dict):
        value = details.get("email")
        if isinstance(value, str) and value:
            return value
    return None


def metadata_from_event(event: dict) -> dict:
    """Our own metadata, if this event type carries it.

    Documented on checkout and collection events, and copied onto the
    subscription on success. Propagation to *invoice* events is not documented,
    which is why the subscription id is persisted rather than relied upon here.
    """
    data = _data(event)
    for key in ("metadata", "meta"):  # the payment object uses `meta`
        value = data.get(key)
        if isinstance(value, dict) and value:
            return value
    return {}


def status_from_event(event: dict) -> str | None:
    status = _data(event).get("status")
    return status.lower() if isinstance(status, str) else None


def organization_id_from_event(event: dict) -> str | None:
    """Our organization id, if this event carries the checkout metadata.

    Absent on renewal invoices, which is why the subscription mapping exists.
    """
    meta = metadata_from_event(event)
    value = meta.get("organization_id") or meta.get("organizationId")
    if isinstance(value, str) and value:
        return value
    org_id, _plan = _from_reference(_data(event).get("reference"))
    return org_id


def plan_from_event(event: dict) -> tuple[str | None, str | None]:
    """Best-effort (user_id, plan) from an event's own payload.

    Both may be None: a renewal invoice carries neither, and is resolved from
    the stored subscription mapping instead. `reference` is parsed as a fallback
    because create_checkout encodes the user id and plan into it.
    """
    data = _data(event)
    meta = metadata_from_event(event)

    user_id = meta.get("user_id") or meta.get("userId")
    plan = meta.get("plan")

    if not plan:
        plan = plan_for_product(data.get("product_id"))

    if not plan:
        _parsed_org, parsed_plan = _from_reference(data.get("reference"))
        plan = plan or parsed_plan

    if plan not in PLANS:
        plan = None
    return (str(user_id) if user_id else None), plan


def _from_reference(reference) -> tuple[str | None, str | None]:
    """Unpack the "ip_<organization_id>_<plan>_<unix>" reference set by
    create_checkout. Returns (organization_id, plan)."""
    if not isinstance(reference, str) or not reference.startswith("ip_"):
        return None, None
    parts = reference.split("_")
    # ip, organization_id, plan, timestamp — the id is a uuid hex with no
    # underscores, so positional parsing is safe for references we minted.
    if len(parts) < 4:
        return None, None
    org_id, plan = parts[1], parts[2]
    return (org_id or None), (plan if plan in PLANS else None)


def grants_access(event: dict) -> bool:
    """Whether this event should turn paid access ON."""
    etype = event_type(event)
    if etype not in ACTIVATING:
        return False

    # A free/zero-amount checkout emits checkout.completed with
    # payment_status=no_payment_required; that must not unlock a paid plan.
    if etype == "checkout.completed":
        payment_status = _data(event).get("payment_status")
        if payment_status and payment_status != "paid":
            return False

    # A subscription event only grants while its status entitles.
    status = status_from_event(event)
    if etype == "customer.subscription.created" and status:
        return status in ENTITLING_STATUSES
    return True


def revokes_access(event: dict) -> bool:
    """Whether this event should turn paid access OFF.

    `customer.subscription.deleted` always revokes. `customer.subscription.updated`
    revokes only on a status that stops entitling — notably `unpaid`, which is
    where an account configured to "mark unpaid" lands once dunning is
    exhausted. A scheduled cancellation (cancel_at_period_end=true, status still
    active) does NOT revoke: that access is paid for until the period ends.
    """
    etype = event_type(event)
    if etype in DEACTIVATING:
        return True
    if etype == "customer.subscription.updated":
        status = status_from_event(event)
        if status in REVOKING_STATUSES:
            return True
        if status and status not in ENTITLING_STATUSES:
            # e.g. "paused" — undocumented as to entitlement. Surface it rather
            # than silently keeping or removing access.
            logger.warning(
                "Bachs subscription %s has unhandled status %r; leaving access unchanged.",
                subscription_id_from_event(event), status,
            )
    return False


def payment_from_event(event: dict) -> dict:
    """Normalize an event into the fields the Payment row records.

    Amounts stay decimal strings in major units — Bachs never uses minor units,
    so nothing is divided by 100.
    """
    data = _data(event)
    amount = data.get("amount")
    if amount is None:
        # invoice.* events use total / amount_paid instead of amount.
        amount = data.get("amount_paid") or data.get("total")
    return {
        # Already major units ("29.00" means twenty-nine). Parsed to Decimal so
        # it lands in the Numeric column exactly, with no float in between.
        "amount": to_decimal(amount),
        "currency": data.get("currency"),
        "status": (data.get("status") or "").lower() or None,
        "event_type": event_type(event),
        "payment_id": _charge_id(data)
        or data.get("invoice_id")
        or data.get("checkout_id"),
        "subscription_id": subscription_id_from_event(event),
    }


def _charge_id(data: dict) -> str | None:
    """The charge identifier, which Bachs spells differently per payload.

    `collection.*` events use a flat `data.charge_id`; `checkout.completed`
    nests the charge and calls it `charge.id` (ch_...); the checkout GET
    response calls the same thing `charge.payment_id` (pay_...).
    """
    flat = data.get("charge_id")
    if isinstance(flat, str) and flat:
        return flat
    charge = data.get("charge")
    if isinstance(charge, dict):
        for key in ("id", "payment_id", "charge_id"):
            value = charge.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def list_subscriptions(customer_id: str) -> list[dict]:
    """All subscriptions for a Bachs customer."""
    data = _get(f"/v1/subscriptions?customer_id={customer_id}&limit=100")
    items = data.get("items")
    return items if isinstance(items, list) else []


def fetch_subscription(subscription_id: str) -> dict:
    """One subscription. Note the object spells its id `id`, while the webhook
    payloads spell the same value `subscription_id`."""
    return _get(f"/v1/subscriptions/{subscription_id}")


def entitled_plan_from_subscription(sub: dict) -> str | None:
    """The plan a subscription object currently entitles, or None.

    Reads the status rather than assuming an existing subscription is live: a
    canceled or unpaid subscription entitles nothing even though the record
    still exists.
    """
    if not isinstance(sub, dict):
        return None
    status = (sub.get("status") or "").lower()
    if status not in ENTITLING_STATUSES:
        return None
    product = sub.get("product")
    product_id = (
        product.get("id") if isinstance(product, dict) else product
    ) or sub.get("product_id")
    if not product_id:
        # Fall back to the first cart item, which is where a multi-item
        # subscription records its product.
        items = sub.get("items")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                product_id = first.get("product_id") or (
                    (first.get("product") or {}).get("id")
                    if isinstance(first.get("product"), dict)
                    else None
                )
    return plan_for_product(product_id if isinstance(product_id, str) else None)


def verify_checkout(checkout_id: str) -> dict:
    """Confirm a checkout the browser was just redirected back from.

    Bachs appends ?checkout_id= to success_url (Paystack used ?reference=), so
    this is what the post-checkout return page has to work with. Verifying
    server-side activates the plan immediately instead of racing the webhook,
    and is idempotent with it.

    Returns a normalized dict; `paid` is the only field that should gate access.
    """
    session = retrieve_checkout(checkout_id)

    charge = session.get("charge")
    charge = charge if isinstance(charge, dict) else {}
    customer = session.get("customer")
    customer = customer if isinstance(customer, dict) else {}
    details = session.get("customer_details")
    details = details if isinstance(details, dict) else {}
    metadata = session.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}

    status = (session.get("status") or "").lower()
    payment_status = (session.get("payment_status") or "").lower()
    charge_status = (charge.get("status") or "").lower()

    # Paid only on an explicit signal. An `open` checkout with no charge is a
    # customer who reached the page and has not paid, and must not be treated as
    # paid just because the session exists.
    paid = payment_status == "paid" or (
        bool(charge) and charge_status in {s.lower() for s in SUCCESS_STATUSES}
    )

    plan = metadata.get("plan")
    if plan not in PLANS:
        plan = None
    if not plan:
        plan = plan_for_product(_product_in_session(session))
    if not plan:
        _ref_user, ref_plan = _from_reference(session.get("reference"))
        plan = ref_plan

    return {
        "checkout_id": session.get("checkout_id") or checkout_id,
        "status": status,
        "paid": paid,
        "plan": plan,
        "organization_id": (
            metadata.get("organization_id")
            or _from_reference(session.get("reference"))[0]
        ),
        "user_id": metadata.get("user_id"),
        "subscription_id": charge.get("subscription_id"),
        "customer_id": customer.get("id") or customer.get("customer_id"),
        "email": customer.get("email") or details.get("email"),
        "amount": session.get("amount") or charge.get("amount"),
        "currency": session.get("currency") or charge.get("currency"),
        # The checkout object calls it payment_id (pay_...); events call the same
        # thing charge.id (ch_...). Either is fine as a dedupe key.
        "payment_id": charge.get("payment_id") or charge.get("id") or session.get("checkout_id"),
    }


def _product_in_session(session: dict) -> str | None:
    """Pull a product id out of a retrieved checkout session."""
    products = session.get("products")
    if isinstance(products, list):
        for entry in products:
            if isinstance(entry, dict):
                candidate = entry.get("product_id") or entry.get("id")
                if isinstance(candidate, str) and candidate:
                    return candidate
            elif isinstance(entry, str) and entry:
                return entry
    cart = session.get("product_cart")
    if isinstance(cart, list):
        for entry in cart:
            if isinstance(entry, dict):
                candidate = entry.get("product_id")
                if isinstance(candidate, str) and candidate:
                    return candidate
    return None
