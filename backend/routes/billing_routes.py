"""Usage and billing endpoints.

Billing supports two modes:
  - Demo mode (no DODO_API_KEY): plan changes apply instantly via /upgrade.
  - Live mode: /checkout opens a Dodo Payments hosted checkout, and the plan is
    applied by /webhook when Dodo confirms the payment.
"""
from flask import Blueprint, current_app, g, jsonify, request

import billing
from auth import login_required
from extensions import db
from models import Extraction, User
from plans import PLANS, build_usage, start_of_month

billing_bp = Blueprint("billing", __name__, url_prefix="/api")


def _count_usage(user: User) -> int:
    return (
        Extraction.query.filter(
            Extraction.user_id == user.id,
            Extraction.status == "completed",
            Extraction.created_at >= start_of_month(),
        ).count()
    )


@billing_bp.get("/usage")
@login_required
def usage():
    return jsonify({"usage": build_usage(_count_usage(g.user), g.user.plan)})


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

    return_url = f'{current_app.config["APP_URL"].rstrip("/")}/dashboard/billing?checkout=success'
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


@billing_bp.post("/billing/webhook")
def webhook():
    """Receive Dodo Payments webhooks (signature-verified) and apply plan changes."""
    try:
        event = billing.verify_webhook(request.headers, request.get_data())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    event_type = event.get("type") or event.get("event_type") or ""
    user_id, plan = billing.plan_from_event(event)

    if user_id:
        user = User.query.get(user_id)
        if user:
            if event_type in _ACTIVATING and plan:
                user.plan = plan
                db.session.commit()
            elif event_type in _DEACTIVATING:
                user.plan = "free"
                db.session.commit()

    # Always 200 so Dodo doesn't retry for events we intentionally ignore.
    return jsonify({"received": True})
