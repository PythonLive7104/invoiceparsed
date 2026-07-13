"""Usage and billing endpoints.

Billing supports two modes:
  - Demo mode (no PAYSTACK_SECRET_KEY): plan changes apply instantly via /upgrade.
  - Live mode: /checkout opens a Paystack hosted checkout. The plan is applied by
    /verify when the browser returns with the transaction reference, and again
    (idempotently) by /webhook when Paystack confirms the charge — whichever
    lands first.
"""
import logging

from flask import Blueprint, current_app, g, jsonify, request

import billing
from auth import login_required
from emails import send_payment_receipt, send_plan_changed
from extensions import db
from models import Payment, User
from plans import PLANS
from usage import usage_for

billing_bp = Blueprint("billing", __name__, url_prefix="/api")
logger = logging.getLogger(__name__)


@billing_bp.get("/usage")
@login_required
def usage():
    return jsonify({"usage": usage_for(g.user)})


@billing_bp.get("/billing/config")
def billing_config():
    """Tells the frontend whether real checkout is available or it's demo mode."""
    return jsonify({"provider": "paystack", "live": billing.is_configured()})


@billing_bp.post("/billing/checkout")
@login_required
def checkout():
    """Start a real Paystack checkout when configured; otherwise fall back to the
    instant demo switch so the flow stays clickable in dev."""
    data = request.get_json(silent=True) or {}
    plan = data.get("plan")
    if plan not in PLANS:
        return jsonify({"error": "Invalid plan."}), 400

    # Downgrades / switching to Free don't go through checkout.
    if plan == "free" or not billing.is_configured():
        g.user.plan = plan
        db.session.commit()
        send_plan_changed(g.user.email, plan, g.user.name)
        return jsonify({"user": g.user.public(), "demo": True})

    # Paystack redirects here after checkout and appends ?reference=…; we add the
    # intended plan so the return page can confirm the right plan activated.
    return_url = f'{current_app.config["APP_URL"].rstrip("/")}/dashboard/billing/return?plan={plan}'
    try:
        url = billing.create_checkout(g.user, plan, return_url)
    except billing.BillingError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"url": url})


@billing_bp.post("/billing/upgrade")
@login_required
def upgrade():
    """Demo instant plan switch (kept for the demo experience / non-live setups)."""
    data = request.get_json(silent=True) or {}
    plan = data.get("plan")
    if plan not in PLANS:
        return jsonify({"error": "Invalid plan."}), 400

    g.user.plan = plan
    db.session.commit()
    send_plan_changed(g.user.email, plan, g.user.name)
    return jsonify({"user": g.user.public(), "demo": True})


# Paystack event types that mean "this subscription is now paid/active". charge.success
# fires for the first charge and every renewal; subscription.create only fires once the
# initial charge has succeeded, so neither can grant access before payment.
_ACTIVATING = {"charge.success", "subscription.create"}
# ...and that mean "access should drop back to free". subscription.not_renew is NOT
# here: it means the user cancelled but keeps access until the period ends, at which
# point Paystack sends subscription.disable.
_DEACTIVATING = {"subscription.disable"}


def _payment_history(user):
    rows = (
        Payment.query.filter_by(user_id=user.id)
        .order_by(Payment.created_at.desc())
        .limit(50)
        .all()
    )
    return [p.public() for p in rows]


@billing_bp.get("/billing/payments")
@login_required
def payments():
    """Return the signed-in user's payment history (most recent first)."""
    return jsonify({"payments": _payment_history(g.user)})


def _upsert_payment(user, details, event_type):
    """Insert or refresh the Payment row for a Paystack transaction.

    De-duplicated on Paystack's transaction reference, so a webhook retry, a return-page
    verify, and a sync can all report the same charge without duplicating it. Returns
    True if the row is new (the caller emails a receipt only then).
    """
    payment_id = details.get("payment_id")
    row = (
        Payment.query.filter_by(provider_payment_id=payment_id).first()
        if payment_id
        else None
    )
    is_new = row is None
    if is_new:
        row = Payment(user_id=user.id, provider_payment_id=payment_id)
        if details.get("created_at"):
            row.created_at = details["created_at"]
        db.session.add(row)

    row.plan = details.get("plan") or row.plan
    row.amount = details.get("amount")
    row.currency = details.get("currency")
    row.status = details.get("status") or event_type
    row.event_type = event_type
    row.provider_subscription_id = (
        details.get("subscription_id") or row.provider_subscription_id
    )
    return is_new


def _record_payment(user, details, event_type):
    """Save a charge and email a receipt the first time we see a successful one."""
    is_new = _upsert_payment(user, details, event_type)
    amount, status = details.get("amount"), details.get("status")
    if is_new and status in billing.SUCCESS_STATUSES and amount is not None:
        # Paystack reports amounts in the smallest currency unit (cents/kobo).
        send_payment_receipt(
            user.email,
            amount / 100,
            details.get("currency"),
            details.get("plan"),
            details.get("payment_id"),
            user.name,
        )


def _activate(user, plan, source):
    """Move the user onto `plan` and email them, unless they're already on it."""
    if not plan or user.plan == plan:
        return None
    user.plan = plan
    logger.info("Activated plan=%s for user_id=%s via %s", plan, user.id, source)
    return plan


@billing_bp.post("/billing/verify")
@login_required
def verify():
    """Confirm a transaction the user was just redirected back with.

    Paystack appends ?reference=… to the callback URL. Verifying it server-side lets us
    activate the plan immediately rather than waiting for the webhook, which is what the
    post-checkout return page depends on. Idempotent with the webhook.
    """
    data = request.get_json(silent=True) or {}
    reference = data.get("reference")
    if not reference:
        return jsonify({"error": "Missing transaction reference."}), 400
    if not billing.is_configured():
        return jsonify({"error": "Paystack is not configured."}), 400

    try:
        txn = billing.verify_transaction(reference)
    except billing.BillingError as exc:
        logger.warning("Verify failed for reference=%s: %s", reference, exc)
        return jsonify({"error": str(exc)}), 502

    details = billing.payment_from_transaction(txn)
    # Only trust a transaction we can tie back to this account, so a reference
    # guessed or replayed from another user can't upgrade the caller.
    owner_id, _ = billing.plan_from_event(txn)
    owner_email = (billing.customer_email_from_event(txn) or "").lower()
    if owner_id != g.user.id and owner_email != (g.user.email or "").lower():
        logger.warning(
            "User %s tried to verify reference=%s belonging to someone else",
            g.user.id,
            reference,
        )
        return jsonify({"error": "That transaction belongs to another account."}), 403

    status = details.get("status")
    activated = None
    if status in billing.SUCCESS_STATUSES:
        _record_payment(g.user, details, "charge.success")
        activated = _activate(g.user, details.get("plan"), "checkout return")

    db.session.commit()
    if activated:
        send_plan_changed(g.user.email, activated, g.user.name)
    return jsonify({"status": status, "user": g.user.public()})


@billing_bp.post("/billing/sync")
@login_required
def sync():
    """Reconcile the user's billing against Paystack on demand ("Confirm payment").

    Pulls their real transactions and active subscription from Paystack's API, records
    any we hadn't seen (e.g. a missed webhook), and activates the plan if an entitling
    subscription exists. Lets a paid user self-recover without waiting on a webhook.
    """
    if not billing.is_configured():
        # Demo mode — nothing to reconcile against; just return what we have.
        return jsonify({"payments": _payment_history(g.user), "user": g.user.public()})

    try:
        remote = billing.fetch_customer_billing(g.user)
    except billing.BillingError as exc:
        logger.warning("Billing sync failed for user_id=%s: %s", g.user.id, exc)
        return jsonify({"error": str(exc)}), 502

    for p in remote["payments"]:
        if p.get("payment_id"):
            _upsert_payment(g.user, p, "sync")

    # Activate the plan from the live subscription, if any.
    activated = _activate(g.user, remote.get("active_plan"), "billing sync")

    db.session.commit()
    if activated:
        send_plan_changed(g.user.email, activated, g.user.name)
    return jsonify({"payments": _payment_history(g.user), "user": g.user.public()})


@billing_bp.post("/billing/webhook")
def webhook():
    """Receive Paystack webhooks (signature-verified) and apply plan changes."""
    try:
        event = billing.verify_webhook(request.headers, request.get_data())
    except ValueError as exc:
        # A signature failure here is the #1 reason a paid plan never activates —
        # log loudly so it's visible without a debugger.
        logger.warning("Paystack webhook REJECTED: %s", exc)
        return jsonify({"error": str(exc)}), 400

    event_type = event.get("event") or ""
    user_id, plan = billing.plan_from_event(event)
    email = billing.customer_email_from_event(event)
    logger.info(
        "Paystack webhook received: event=%s user_id=%s plan=%s", event_type, user_id, plan
    )

    # charge.success carries our checkout metadata; subscription.* events don't, so
    # fall back to the Paystack customer's email.
    user = User.query.get(user_id) if user_id else None
    if user is None and email:
        user = User.query.filter(db.func.lower(User.email) == email.lower()).first()
    if user is None:
        # Can't map the charge to an account. Happens when checkout was started
        # outside the app (e.g. a Paystack payment page), which attaches no metadata.
        logger.warning(
            "Paystack webhook %s could not be mapped to an account (user_id=%s email=%s).",
            event_type,
            user_id,
            email,
        )
        return jsonify({"received": True})

    # Record any charge so it appears in the user's billing history, whether or
    # not it changes the plan.
    if event_type.startswith("charge."):
        _record_payment(user, billing.payment_from_event(event), event_type)

    new_plan = None
    if event_type in _ACTIVATING:
        new_plan = _activate(user, plan, event_type)
    elif event_type in _DEACTIVATING and user.plan != "free":
        new_plan = "free"
        user.plan = "free"
        logger.info("Downgraded user_id=%s to free via %s", user.id, event_type)

    db.session.commit()
    if new_plan:
        send_plan_changed(user.email, new_plan, user.name)
    # Always 200 so Paystack doesn't retry for events we intentionally ignore.
    return jsonify({"received": True})
