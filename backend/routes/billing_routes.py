"""Usage and billing endpoints.

Billing supports two modes:
  - Demo mode (no DODO_API_KEY): plan changes apply instantly via /upgrade.
  - Live mode: /checkout opens a Dodo Payments hosted checkout, and the plan is
    applied by /webhook when Dodo confirms the payment.
"""
import logging

from flask import Blueprint, current_app, g, jsonify, request

import billing
from auth import login_required
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
    return jsonify({"provider": "dodo", "live": billing.is_configured()})


@billing_bp.post("/billing/checkout")
@login_required
def checkout():
    """Start a real Dodo checkout when configured; otherwise fall back to the
    instant demo switch so the flow stays clickable in dev."""
    data = request.get_json(silent=True) or {}
    plan = data.get("plan")
    if plan not in PLANS:
        return jsonify({"error": "Invalid plan."}), 400

    # Downgrades / switching to Free don't go through checkout.
    if plan == "free" or not billing.is_configured():
        g.user.plan = plan
        db.session.commit()
        return jsonify({"user": g.user.public(), "demo": True})

    # Dodo redirects here after checkout and appends its own status params; we add
    # the intended plan so the return page can confirm the right plan activated.
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
    return jsonify({"user": g.user.public(), "demo": True})


# Dodo event types that mean "this subscription is now paid/active". We grant
# only on confirmed-payment events — NOT subscription.created, which can fire
# before payment completes.
_ACTIVATING = {"subscription.active", "payment.succeeded"}
# ...and that mean "access should drop back to free".
_DEACTIVATING = {"subscription.cancelled", "subscription.canceled", "subscription.expired"}


@billing_bp.get("/billing/payments")
@login_required
def payments():
    """Return the signed-in user's payment history (most recent first)."""
    rows = (
        Payment.query.filter_by(user_id=g.user.id)
        .order_by(Payment.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify({"payments": [p.public() for p in rows]})


def _record_payment(user, plan, event_type, event):
    """Save a Payment row for this event, de-duplicating on Dodo's payment id."""
    details = billing.payment_from_event(event)
    payment_id = details.get("payment_id")
    if payment_id and Payment.query.filter_by(provider_payment_id=payment_id).first():
        return  # already recorded (Dodo retried this delivery)
    db.session.add(Payment(
        user_id=user.id,
        plan=plan,
        amount=details.get("amount"),
        currency=details.get("currency"),
        status=details.get("status") or event_type,
        event_type=event_type,
        provider_payment_id=payment_id,
        provider_subscription_id=details.get("subscription_id"),
    ))


@billing_bp.post("/billing/webhook")
def webhook():
    """Receive Dodo Payments webhooks (signature-verified) and apply plan changes."""
    try:
        event = billing.verify_webhook(request.headers, request.get_data())
    except ValueError as exc:
        # A signature/timestamp failure here is the #1 reason a paid plan never
        # activates — log loudly so it's visible without a debugger.
        logger.warning("Dodo webhook REJECTED: %s", exc)
        return jsonify({"error": str(exc)}), 400

    event_type = event.get("type") or event.get("event_type") or ""
    user_id, plan = billing.plan_from_event(event)
    logger.info(
        "Dodo webhook received: type=%s user_id=%s plan=%s", event_type, user_id, plan
    )

    if not user_id:
        # No metadata means we can't map the charge to an account. This happens
        # when checkout was started outside the app (e.g. a dashboard payment
        # link), which doesn't attach our user_id/plan metadata.
        logger.warning(
            "Dodo webhook %s has no user_id metadata — cannot map to an account.",
            event_type,
        )
        return jsonify({"received": True})

    user = User.query.get(user_id)
    if not user:
        logger.warning("Dodo webhook references unknown user_id=%s", user_id)
        return jsonify({"received": True})

    # Record any charge so it appears in the user's billing history, whether or
    # not it changes the plan.
    if event_type in _ACTIVATING or event_type.startswith("payment."):
        _record_payment(user, plan, event_type, event)

    if event_type in _ACTIVATING and plan:
        user.plan = plan
        logger.info("Activated plan=%s for user_id=%s via %s", plan, user.id, event_type)
    elif event_type in _DEACTIVATING:
        user.plan = "free"
        logger.info("Downgraded user_id=%s to free via %s", user.id, event_type)

    db.session.commit()
    # Always 200 so Dodo doesn't retry for events we intentionally ignore.
    return jsonify({"received": True})
