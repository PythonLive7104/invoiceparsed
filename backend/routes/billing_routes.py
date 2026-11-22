"""Usage and billing endpoints. Bachs is the only payment provider.

Two modes:
  - Demo mode (BILLING_DEMO_MODE=true and no Bachs key): /upgrade switches plans
    instantly with no payment, for local development and the hosted demo.
  - Live mode (BACHS_SECRET_KEY set): /checkout opens a Bachs hosted checkout.
    The plan is applied by /verify when the browser returns with ?checkout_id=,
    and again — idempotently — by /webhook when Bachs confirms the charge,
    whichever lands first.

With neither configured, plan changes are REFUSED rather than granted. A deploy
that has lost its provider key must fail closed; inferring "demo mode" from "no
keys" turned a misconfiguration into a free upgrade to any plan.

Amounts are decimal values in major units throughout, because that is what Bachs
reports and what Payment.amount stores. Nothing here divides by 100.
"""
import logging
from datetime import datetime

from flask import Blueprint, current_app, g, jsonify, request

import bachs
from auth import login_required
from emails import send_payment_receipt, send_plan_changed
from extensions import db
from models import Organization, Payment, ProviderEvent, Subscription, User
from money import to_decimal
from plans import PLANS
from roles import BILLING_MANAGE, BILLING_READ
from stats import dashboard_stats
from tenancy import (
    current_organization,
    default_membership,
    require_permission,
    scoped,
)
from usage import usage_for

billing_bp = Blueprint("billing", __name__, url_prefix="/api")
logger = logging.getLogger(__name__)

# Lower-cased once: provider status strings vary in case between payloads
# (collection.* reports "SUCCEEDED", invoice.* reports "paid").
_SUCCESS = {s.lower() for s in bachs.SUCCESS_STATUSES}


@billing_bp.get("/usage")
@login_required
def usage():
    return jsonify({"usage": usage_for(current_organization())})


@billing_bp.get("/usage/stats")
@login_required
def usage_stats():
    """Processing statistics for the dashboard.

    Not permission-gated beyond membership: every member should be able to see
    how much of the shared allowance is left and whether anything needs their
    attention. It exposes counts, never document contents.
    """
    return jsonify(dashboard_stats(current_organization()))


# ─── Guards ──────────────────────────────────────────────────────────────────
def _plan_change_allowed():
    """None if an unpaid plan switch is permitted here, else an error response.

    Unpaid switching exists for local development and the hosted demo. It is
    gated on BILLING_DEMO_MODE being explicitly on, so a production deploy
    missing its provider key refuses to change plans instead of handing out paid
    tiers for free.
    """
    if bachs.is_configured():
        return (
            jsonify({
                "error": "Plan changes must go through checkout.",
                "code": "CHECKOUT_REQUIRED",
            }),
            403,
        )
    if not current_app.config.get("BILLING_DEMO_MODE", False):
        logger.error(
            "Plan change refused: no payment provider is configured and "
            "BILLING_DEMO_MODE is off. Set BACHS_SECRET_KEY (or "
            "BILLING_DEMO_MODE=true for local development)."
        )
        return (
            jsonify({
                "error": "Billing is temporarily unavailable. Please try again later.",
                "code": "BILLING_UNAVAILABLE",
            }),
            503,
        )
    return None


@billing_bp.get("/billing/config")
def billing_config():
    """Tells the frontend whether real checkout is available, or it's demo mode."""
    return jsonify({"provider": bachs.PROVIDER, "live": bachs.is_configured()})


# ─── Checkout ────────────────────────────────────────────────────────────────
@billing_bp.post("/billing/checkout")
@login_required
@require_permission(BILLING_MANAGE)
def checkout():
    data = request.get_json(silent=True) or {}
    plan = data.get("plan")
    if plan not in PLANS:
        return jsonify({"error": "Invalid plan."}), 400

    # Switching to Free is a downgrade and costs nothing, so it never needs a
    # payment provider — a billing outage must not trap someone on a paid plan.
    if plan == "free":
        return _apply_free_downgrade()

    if not bachs.is_configured():
        refusal = _plan_change_allowed()
        if refusal is not None:
            return refusal
        organization = current_organization()
        organization.plan = plan
        db.session.commit()
        send_plan_changed(g.user.email, plan, g.user.name)
        return jsonify({
            "user": g.user.public(),
            "organization": organization.public(),
            "demo": True,
        })

    app_url = current_app.config["APP_URL"].rstrip("/")
    try:
        url = bachs.create_checkout(
            current_organization(),
            g.user,
            plan,
            f"{app_url}/dashboard/billing/return?plan={plan}",
            cancel_url=f"{app_url}/dashboard/billing",
        )
    except bachs.BachsAccountNotActivated as exc:
        # 503, not 502: this is our own account not being live yet, and it will
        # stay broken until someone finishes onboarding. A distinct code lets
        # the UI say something useful instead of "payment failed".
        logger.error(
            "Bachs checkout refused - the Bachs account is not activated for "
            "live payments. Finish onboarding, or set BACHS_SECRET_KEY to an "
            "sk_sandbox_ key with BACHS_API_BASE=https://sandbox-api.bachs.io "
            "to test. (user_id=%s)", g.user.id,
        )
        return jsonify({"error": str(exc), "code": "PAYMENTS_UNAVAILABLE"}), 503
    except bachs.BachsError as exc:
        logger.warning("Bachs checkout failed for user_id=%s: %s", g.user.id, exc)
        return jsonify({"error": str(exc), "code": "CHECKOUT_FAILED"}), 502
    return jsonify({"url": url})


def _apply_free_downgrade():
    """Drop to Free, scheduling any live subscription to stop at period end.

    Cancelled at period end rather than immediately: the customer has already
    paid for the current period. Bachs sends customer.subscription.deleted when
    it actually lapses, and that is what finally removes access.
    """
    organization = current_organization()
    if bachs.is_configured():
        for row in scoped(Subscription).all():
            if row.status in bachs.ENTITLING_STATUSES:
                try:
                    bachs.cancel_subscription(
                        row.provider_subscription_id, at_period_end=True
                    )
                    row.cancel_at_period_end = True
                except bachs.BachsError as exc:
                    # Don't fail the downgrade on a provider hiccup; the webhook
                    # or a later sync reconciles. Logged so it stays visible.
                    logger.warning(
                        "Could not cancel Bachs subscription %s for user_id=%s: %s",
                        row.provider_subscription_id, g.user.id, exc,
                    )
    organization.plan = "free"
    db.session.commit()
    send_plan_changed(g.user.email, "free", g.user.name)
    return jsonify({
        "user": g.user.public(),
        "organization": organization.public(),
        "demo": not bachs.is_configured(),
    })


@billing_bp.post("/billing/upgrade")
@login_required
@require_permission(BILLING_MANAGE)
def upgrade():
    """Demo instant plan switch — only when no payment provider is configured."""
    refusal = _plan_change_allowed()
    if refusal is not None:
        return refusal

    data = request.get_json(silent=True) or {}
    plan = data.get("plan")
    if plan not in PLANS:
        return jsonify({"error": "Invalid plan."}), 400

    organization = current_organization()
    organization.plan = plan
    db.session.commit()
    send_plan_changed(g.user.email, plan, g.user.name)
    return jsonify({
        "user": g.user.public(),
        "organization": organization.public(),
        "demo": True,
    })


# ─── Payments ────────────────────────────────────────────────────────────────
def _payment_history(organization):
    rows = (
        Payment.query.filter_by(organization_id=organization.id)
        .order_by(Payment.created_at.desc())
        .limit(50)
        .all()
    )
    return [p.public() for p in rows]


@billing_bp.get("/billing/payments")
@login_required
@require_permission(BILLING_READ)
def payments():
    """The signed-in user's payment history (most recent first)."""
    return jsonify({"payments": _payment_history(current_organization())})


def _upsert_payment(organization, user, details, event_type):
    """Insert or refresh the Payment row for a charge.

    De-duplicated on the provider's payment id, so a webhook retry, a
    return-page verify and a sync can all report the same charge without
    duplicating it. Returns True if the row is new (the caller emails a receipt
    only then).
    """
    payment_id = details.get("payment_id")
    row = (
        Payment.query.filter_by(provider_payment_id=payment_id).first()
        if payment_id
        else None
    )
    is_new = row is None
    if is_new:
        row = Payment(
            organization_id=organization.id,
            user_id=user.id,
            provider_payment_id=payment_id,
        )
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


def _record_payment(organization, user, details, event_type):
    """Save a charge, and email a receipt the first time a successful one is seen."""
    is_new = _upsert_payment(organization, user, details, event_type)
    amount = details.get("amount")
    status = (details.get("status") or "").lower()
    if is_new and status in _SUCCESS and amount is not None:
        # Already major units — do NOT divide by 100. Bachs reports decimal
        # major units and Payment.amount stores them that way.
        send_payment_receipt(
            user.email,
            amount,
            details.get("currency"),
            details.get("plan"),
            details.get("payment_id"),
            user.name,
        )


def _activate(organization, plan, source):
    """Move the organization onto `plan`, unless it is already there."""
    if not plan or organization.plan == plan:
        return None
    organization.plan = plan
    logger.info(
        "Activated plan=%s for organization_id=%s via %s", plan, organization.id, source
    )
    return plan


def _remember_subscription(organization, user, *, subscription_id, customer_id=None, plan=None,
                           status=None, cancel_at_period_end=None,
                           current_period_end=None, event_at=None):
    """Record or refresh the user <-> provider subscription mapping.

    This is what lets a renewal invoice — which carries none of our metadata —
    be attributed to the right account months later.
    """
    if not subscription_id:
        return None
    row = Subscription.query.filter_by(provider_subscription_id=subscription_id).first()
    if row is None:
        row = Subscription(
            organization_id=organization.id,
            user_id=user.id,
            provider=bachs.PROVIDER,
            provider_subscription_id=subscription_id,
        )
        db.session.add(row)
    row.organization_id = organization.id
    row.user_id = user.id
    if customer_id:
        row.provider_customer_id = customer_id
    if plan:
        row.plan = plan
    if status:
        row.status = status
    if isinstance(cancel_at_period_end, bool):
        row.cancel_at_period_end = cancel_at_period_end
    if current_period_end:
        row.current_period_end = current_period_end
    if event_at:
        row.last_event_at = event_at
    return row


# ─── Return page: verify a completed checkout ────────────────────────────────
@billing_bp.post("/billing/verify")
@login_required
@require_permission(BILLING_MANAGE)
def verify():
    """Confirm the checkout the browser was just redirected back from.

    Bachs appends ?checkout_id= to success_url. Verifying server-side activates
    the plan on the spot rather than racing the webhook, and is idempotent with
    it. `reference` is still accepted as a body key so an older deployed
    frontend keeps working during a rollout.
    """
    data = request.get_json(silent=True) or {}
    checkout_id = data.get("checkout_id") or data.get("reference")
    if not checkout_id:
        return jsonify({"error": "Missing checkout id."}), 400
    if not bachs.is_configured():
        return jsonify({"error": "Billing is not configured.",
                        "code": "BILLING_UNAVAILABLE"}), 503

    try:
        result = bachs.verify_checkout(checkout_id)
    except bachs.BachsError as exc:
        logger.warning("Verify failed for checkout_id=%s: %s", checkout_id, exc)
        return jsonify({"error": str(exc)}), 502

    # Only trust a checkout that ties back to the acting organization, so an id
    # guessed or replayed from another tenant cannot upgrade the caller.
    organization = current_organization()
    owner_org = result.get("organization_id")
    owner_email = (result.get("email") or "").lower()
    if owner_org != organization.id and owner_email != (g.user.email or "").lower():
        logger.warning(
            "User %s tried to verify checkout_id=%s belonging to someone else",
            g.user.id, checkout_id,
        )
        return jsonify({"error": "That checkout does not belong to this account."}), 403

    if not result.get("paid"):
        # Reached the return page without paying, or the charge is still
        # settling. The webhook will finish the job if it completes.
        return jsonify({"status": result.get("status") or "pending",
                        "user": g.user.public()}), 200

    plan = result.get("plan")
    _remember_subscription(
        organization,
        g.user,
        subscription_id=result.get("subscription_id"),
        customer_id=result.get("customer_id"),
        plan=plan,
        status="active",
    )
    activated = (
        _activate(organization, plan, "checkout verify") if plan and plan != "free" else None
    )
    if result.get("payment_id") and result.get("amount") is not None:
        _record_payment(
            organization,
            g.user,
            {
                "payment_id": result["payment_id"],
                "amount": to_decimal(result.get("amount")),
                "currency": result.get("currency"),
                "status": "succeeded",
                "plan": plan,
                "subscription_id": result.get("subscription_id"),
            },
            "checkout.verify",
        )
    db.session.commit()
    if activated:
        send_plan_changed(g.user.email, activated, g.user.name)
    return jsonify({"status": "success", "user": g.user.public()})


# ─── Self-service reconcile ──────────────────────────────────────────────────
@billing_bp.post("/billing/sync")
@login_required
@require_permission(BILLING_READ)
def sync():
    """Reconcile this account against Bachs on demand ("Confirm payment").

    Re-reads every subscription we know about and applies whatever it currently
    entitles, so a paid user can self-recover from a missed webhook instead of
    waiting for the next renewal.

    Uses only documented endpoints. There is no charge-listing call here, so
    this reconciles *entitlement*, not payment history.
    """
    if not bachs.is_configured():
        organization = current_organization()
        return jsonify({
            "payments": _payment_history(organization),
            "user": g.user.public(),
            "organization": organization.public(),
        })

    organization = current_organization()
    rows = scoped(Subscription).all()
    entitled = None
    read_any = False
    for row in rows:
        try:
            remote = bachs.fetch_subscription(row.provider_subscription_id)
        except bachs.BachsError as exc:
            logger.warning(
                "Billing sync could not read subscription %s: %s",
                row.provider_subscription_id, exc,
            )
            continue
        read_any = True
        status = (remote.get("status") or "").lower()
        if status:
            row.status = status
        cancel_at_period_end = remote.get("cancel_at_period_end")
        if isinstance(cancel_at_period_end, bool):
            row.cancel_at_period_end = cancel_at_period_end
        plan = bachs.entitled_plan_from_subscription(remote)
        if plan:
            row.plan = plan
            entitled = _best_plan(entitled, plan)

    activated = None
    if entitled:
        activated = _activate(organization, entitled, "billing sync")
    elif read_any and organization.plan != "free":
        # Every subscription we could read has stopped entitling, so a cancelled
        # account cannot keep paid access through a missed webhook. Guarded on
        # read_any: if every read FAILED we know nothing, and must not downgrade
        # a paying customer because of a provider outage.
        logger.info(
            "Billing sync: no entitling subscription for organization_id=%s",
            organization.id,
        )
        organization.plan = "free"
        activated = "free"

    db.session.commit()
    if activated:
        send_plan_changed(g.user.email, activated, g.user.name)
    return jsonify({
        "payments": _payment_history(organization),
        "user": g.user.public(),
        "organization": organization.public(),
    })


def _best_plan(current, candidate):
    """The higher of two plans, so several live subscriptions cannot downgrade."""
    order = list(PLANS.keys())
    if current is None:
        return candidate
    try:
        return candidate if order.index(candidate) > order.index(current) else current
    except ValueError:
        return current


# ─── Subscription management ─────────────────────────────────────────────────
def _current_subscription():
    """The acting organization's most recent subscription."""
    return scoped(Subscription).order_by(Subscription.created_at.desc()).first()


@billing_bp.get("/billing/subscription")
@login_required
@require_permission(BILLING_READ)
def subscription():
    """The account's current subscription, for the billing page."""
    row = _current_subscription()
    return jsonify({"subscription": row.public() if row else None})


@billing_bp.post("/billing/cancel")
@login_required
@require_permission(BILLING_MANAGE)
def cancel():
    """Cancel at the end of the paid period.

    Not immediate: the customer has paid through the current period and keeps
    access until it ends. Bachs then sends customer.subscription.deleted, and
    that is what drops them to Free — so this endpoint deliberately does not
    change their plan.
    """
    if not bachs.is_configured():
        return jsonify({"error": "Billing is not configured.",
                        "code": "BILLING_UNAVAILABLE"}), 503

    row = _current_subscription()
    if row is None or row.status not in bachs.ENTITLING_STATUSES:
        return jsonify({"error": "No active subscription to cancel."}), 404

    try:
        bachs.cancel_subscription(row.provider_subscription_id, at_period_end=True)
    except bachs.BachsError as exc:
        logger.warning(
            "Cancel failed for subscription %s (user_id=%s): %s",
            row.provider_subscription_id, g.user.id, exc,
        )
        return jsonify({"error": str(exc)}), 502

    row.cancel_at_period_end = True
    db.session.commit()
    return jsonify({"subscription": row.public(), "user": g.user.public()})


# ─── Webhook ─────────────────────────────────────────────────────────────────
def _parse_event_time(value):
    """Parse a provider ISO-8601 timestamp. None if unparseable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _already_applied(event) -> bool:
    """True if this event id has been handled before.

    Delivery is at-least-once, so the same event can arrive several times. The
    unique constraint on event_id is the real mechanism: a concurrent duplicate
    loses the insert race, and that is treated as "already applied".
    """
    identifier = bachs.event_id(event)
    if not identifier:
        return False
    if ProviderEvent.query.filter_by(event_id=identifier).first() is not None:
        logger.info("Bachs event %s already applied; skipping.", identifier)
        return True
    db.session.add(ProviderEvent(
        provider=bachs.PROVIDER,
        event_id=identifier,
        event_type=bachs.event_type(event),
    ))
    try:
        db.session.flush()
    except Exception:
        db.session.rollback()
        logger.info("Bachs event %s is already being processed; skipping.", identifier)
        return True
    return False


def _target_for(event, sub_id, customer_id):
    """Resolve a Bachs event to (organization, user, subscription_row).

    The ORGANIZATION is what matters: it owns the plan, so a renewal has to land
    on the right tenant even if the person who bought the subscription has since
    left the team. The user is only recorded as "who this charge is attributed
    to" and for the notification email.

    Most reliable source first:

    1. metadata.organization_id, set by create_checkout. Present on checkout and
       collection events, and copied onto the subscription on success.
    2. The stored Subscription row — the only thing that can identify a renewal
       invoice, which carries no metadata of ours.
    3. The provider customer id, for events that name the customer only.
    4. The customer email -> that user's personal organization, as a last
       resort: someone may have checked out outside the app, which attaches no
       metadata at all. Deliberately last, because an email match is the weakest
       evidence and could attribute a charge to the wrong tenant if one person
       belongs to several.

    Any of the three may be None.
    """
    row = None
    if sub_id:
        row = Subscription.query.filter_by(provider_subscription_id=sub_id).first()
    if row is None and customer_id:
        row = Subscription.query.filter_by(provider_customer_id=customer_id).first()

    organization = None
    org_id = bachs.organization_id_from_event(event)
    if org_id:
        organization = Organization.query.get(org_id)
    if organization is None and row is not None:
        organization = Organization.query.get(row.organization_id)

    user = None
    user_id, _plan = bachs.plan_from_event(event)
    if user_id:
        user = User.query.get(user_id)
    if user is None and row is not None:
        user = User.query.get(row.user_id)
    if user is None:
        email = bachs.customer_email_from_event(event)
        if email:
            user = User.query.filter(db.func.lower(User.email) == email.lower()).first()

    if organization is None and user is not None:
        # Fall back to this user's personal organization, which is where a solo
        # account's subscription belongs.
        membership = default_membership(user)
        if membership is not None:
            organization = Organization.query.get(membership.organization_id)

    return organization, user, row


@billing_bp.post("/billing/webhook")
def webhook():
    """Receive Bachs webhooks (signature-verified) and apply plan changes.

    Response codes carry weight. Bachs retries 5xx, 408 and 429 but DISCARDS
    other 4xx, and disables the endpoint after 72h of failures. So a bad
    signature is 400 (correctly never retried), our own misconfiguration is 503,
    and an unexpected internal error is 500 — never a swallowed 200, which would
    lose a real payment permanently.
    """
    raw_body = request.get_data()
    try:
        return _handle_webhook(request.headers, raw_body)
    except Exception:
        db.session.rollback()
        logger.exception("Bachs webhook processing failed; asking for a retry.")
        return jsonify({"error": "Webhook processing failed."}), 500


def _handle_webhook(headers, raw_body):
    try:
        event = bachs.verify_webhook(headers, raw_body)
    except bachs.WebhookNotConfigured as exc:
        logger.error("Bachs webhook cannot be verified - %s", exc)
        return jsonify({"error": "Billing webhook not configured.",
                        "code": "BILLING_UNAVAILABLE"}), 503
    except ValueError as exc:
        logger.warning("Bachs webhook REJECTED: %s", exc)
        return jsonify({"error": str(exc)}), 400

    etype = bachs.event_type(event)
    sub_id = bachs.subscription_id_from_event(event)
    customer_id = bachs.customer_id_from_event(event)
    _user_id, plan = bachs.plan_from_event(event)
    logger.info(
        "Bachs webhook: event=%s id=%s subscription=%s plan=%s",
        etype, bachs.event_id(event), sub_id, plan,
    )

    organization, user, row = _target_for(event, sub_id, customer_id)
    if organization is None:
        # Acknowledge: retrying will not make an unknown customer known, and
        # repeated failures would disable the endpoint for everyone else.
        logger.warning(
            "Bachs webhook %s could not be mapped to an organization "
            "(subscription=%s customer=%s).", etype, sub_id, customer_id,
        )
        return jsonify({"status": "unmapped"}), 200

    if _already_applied(event):
        db.session.commit()
        return jsonify({"status": "duplicate"}), 200

    event_at = _parse_event_time(event.get("created_at"))
    if row is None and sub_id:
        row = Subscription.query.filter_by(provider_subscription_id=sub_id).first()

    # Out-of-order guard. Deliveries can arrive reordered, and a delayed
    # customer.subscription.deleted landing after a fresh
    # customer.subscription.created would otherwise revoke a paying customer.
    if row is not None and row.last_event_at and event_at and event_at < row.last_event_at:
        logger.info(
            "Bachs webhook %s ignored as stale (event %s < stored %s).",
            etype, event_at, row.last_event_at,
        )
        db.session.commit()  # keep the ProviderEvent row so it is not reprocessed
        return jsonify({"status": "stale"}), 200

    data = event.get("data") or {}
    plan = plan or (row.plan if row is not None else None)

    _remember_subscription(
        organization,
        user,
        subscription_id=sub_id,
        customer_id=customer_id,
        plan=plan,
        status=bachs.status_from_event(event),
        cancel_at_period_end=data.get("cancel_at_period_end"),
        current_period_end=_parse_event_time(data.get("current_period_end")),
        event_at=event_at,
    )

    activated = None
    if bachs.revokes_access(event):
        if organization.plan != "free":
            logger.info(
                "Bachs: revoking paid access for organization_id=%s (%s)",
                organization.id, etype,
            )
            organization.plan = "free"
            activated = "free"
    elif bachs.grants_access(event) and plan and plan != "free":
        activated = _activate(organization, plan, f"Bachs {etype}")

    details = bachs.payment_from_event(event)
    if details.get("payment_id") and details.get("amount") is not None and user is not None:
        _record_payment(organization, user, dict(details, plan=plan), etype)

    db.session.commit()
    if activated and user is not None:
        send_plan_changed(user.email, activated, user.name)
    return jsonify({"status": "ok"}), 200
