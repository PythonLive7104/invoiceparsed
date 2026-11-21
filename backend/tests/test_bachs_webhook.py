"""The Bachs webhook route end to end.

test_bachs.py covers the provider module in isolation. These tests drive the
actual HTTP endpoint, because the parts most likely to be wrong are the ones
that span the module and the database: resolving a renewal invoice that carries
none of our metadata, revoking on the right event, and surviving deliveries
that arrive out of order.
"""
import hashlib
import hmac
import json
import time

import pytest

import bachs
from tests.conftest import make_user

SECRET = "whsec_" + "c" * 64
WEBHOOK = "/api/billing/webhook"


@pytest.fixture(autouse=True)
def _bachs_live(app, monkeypatch):
    """Make Bachs the configured provider for these tests."""
    monkeypatch.setattr(bachs.Config, "BACHS_SECRET_KEY", "sk_sandbox_test")
    monkeypatch.setattr(bachs.Config, "BACHS_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(bachs.Config, "BACHS_WEBHOOK_TOLERANCE", 300)
    monkeypatch.setattr(bachs.Config, "BACHS_PRODUCTS", {
        "starter": "prod_starter", "pro": "prod_pro", "business": "prod_business",
    })


def _send(client, event):
    body = json.dumps(event).encode("utf-8")
    ts = str(int(time.time()))
    sig = hmac.new(SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return client.post(
        WEBHOOK, data=body,
        headers={"Content-Type": "application/json",
                 "X-Bachs-Signature-V2": f"t={ts},v1={sig}"},
    )


def _event(etype, created_at="2026-04-27T12:00:00Z", **data):
    return {"id": f"evt_{etype}", "type": etype, "created_at": created_at,
            "organization_id": "acct_1", "data": data}


def _plan_of(app, user):
    """The plan lives on the organization now."""
    from models import Organization
    with app.app_context():
        return Organization.query.get(user["organization_id"]).plan


def _sub_row(app, sub_id):
    from models import Subscription
    with app.app_context():
        return Subscription.query.filter_by(provider_subscription_id=sub_id).first()


# ─── Activation ──────────────────────────────────────────────────────────────
def test_checkout_completed_activates_the_plan_from_metadata(client, app):
    user = make_user(app, plan="free")
    r = _send(client, _event(
        "checkout.completed", checkout_id="chk_1", mode="subscription",
        payment_status="paid", amount="49.00", currency="USD",
        subscription={"subscription_id": "sub_1"},
        customer={"customer_id": "cust_1", "email": user["email"]},
        metadata={"user_id": user["id"], "plan": "pro"},
    ))
    assert r.status_code == 200
    assert _plan_of(app, user) == "pro"


def test_subscription_created_records_the_mapping(client, app):
    """The mapping is what makes later renewals resolvable."""
    user = make_user(app, plan="free")
    _send(client, _event(
        "customer.subscription.created", subscription_id="sub_2", status="active",
        product_id="prod_business", currency="USD", amount="99.00",
        customer={"customer_id": "cust_2", "email": user["email"]},
        metadata={"user_id": user["id"], "plan": "business"},
    ))
    assert _plan_of(app, user) == "business"
    row = _sub_row(app, "sub_2")
    assert row is not None
    assert row.user_id == user["id"]
    assert row.provider_customer_id == "cust_2"
    assert row.plan == "business"
    assert row.status == "active"


def test_free_checkout_does_not_grant_a_paid_plan(client, app):
    user = make_user(app, plan="free")
    _send(client, _event(
        "checkout.completed", checkout_id="chk_free", payment_status="no_payment_required",
        customer={"customer_id": "c", "email": user["email"]},
        metadata={"user_id": user["id"], "plan": "business"},
    ))
    assert _plan_of(app, user) == "free"


# ─── The renewal case — the whole reason the mapping table exists ────────────
def test_renewal_invoice_without_metadata_extends_the_right_user(client, app):
    """A renewal carries no metadata and no product id. It must still be matched
    to the user, via the subscription id stored when the subscription began."""
    user = make_user(app, plan="free")
    _send(client, _event(
        "customer.subscription.created", created_at="2026-04-01T00:00:00Z",
        subscription_id="sub_3", status="active", product_id="prod_pro",
        customer={"customer_id": "cust_3", "email": user["email"]},
        metadata={"user_id": user["id"], "plan": "pro"},
    ))
    assert _plan_of(app, user) == "pro"

    # Simulate a downgrade having happened in our DB, then a renewal arriving.
    from extensions import db
    from models import Organization
    with app.app_context():
        org = Organization.query.get(user["organization_id"])
        org.plan = "free"
        db.session.commit()

    r = _send(client, _event(
        "invoice.paid", created_at="2026-05-01T00:00:00Z", invoice_id="inv_1",
        subscription={"subscription_id": "sub_3"}, status="paid",
        total="49.00", currency="USD", period_start="2026-05-01", period_end="2026-06-01",
        customer={"customer_id": "cust_3", "email": "someone-else@example.com"},
        metadata={},
    ))
    assert r.status_code == 200
    # Resolved by subscription id, and the plan came from the stored mapping -
    # note the renewal's email deliberately does NOT match the user.
    assert _plan_of(app, user) == "pro"


def test_unmappable_event_is_acknowledged_not_retried(client, app):
    """Retrying will not make an unknown customer known, and repeated failures
    would disable the endpoint for every other customer."""
    r = _send(client, _event(
        "invoice.paid", invoice_id="inv_x",
        subscription={"subscription_id": "sub_unknown"},
        customer={"customer_id": "cust_unknown", "email": "nobody@example.com"},
    ))
    assert r.status_code == 200
    assert r.get_json()["status"] == "unmapped"


# ─── Revocation ──────────────────────────────────────────────────────────────
def test_subscription_deleted_revokes_access(client, app):
    user = make_user(app, plan="pro")
    _send(client, _event(
        "customer.subscription.created", created_at="2026-04-01T00:00:00Z",
        subscription_id="sub_4", status="active", product_id="prod_pro",
        customer={"customer_id": "cust_4", "email": user["email"]},
        metadata={"user_id": user["id"], "plan": "pro"},
    ))
    r = _send(client, _event(
        "customer.subscription.deleted", created_at="2026-06-01T00:00:00Z",
        subscription_id="sub_4", status="canceled",
        customer={"customer_id": "cust_4", "email": user["email"]},
    ))
    assert r.status_code == 200
    assert _plan_of(app, user) == "free"


def test_scheduled_cancellation_keeps_access_until_the_period_ends(client, app):
    """cancel_at_period_end with status still active means they paid through the
    period. Revoking now would take away access they are owed."""
    user = make_user(app, plan="business")
    _send(client, _event(
        "customer.subscription.created", created_at="2026-04-01T00:00:00Z",
        subscription_id="sub_5", status="active", product_id="prod_business",
        customer={"customer_id": "cust_5", "email": user["email"]},
        metadata={"user_id": user["id"], "plan": "business"},
    ))
    r = _send(client, _event(
        "customer.subscription.updated", created_at="2026-05-01T00:00:00Z",
        subscription_id="sub_5", status="active", cancel_at_period_end=True,
        current_period_end="2026-06-01T00:00:00Z",
        customer={"customer_id": "cust_5", "email": user["email"]},
    ))
    assert r.status_code == 200
    assert _plan_of(app, user) == "business"      # still paid up
    row = _sub_row(app, "sub_5")
    assert row.cancel_at_period_end is True       # but the intent is recorded


def test_unpaid_status_revokes(client, app):
    """Where an account set to "mark unpaid" lands once dunning is exhausted."""
    user = make_user(app, plan="pro")
    _send(client, _event(
        "customer.subscription.created", created_at="2026-04-01T00:00:00Z",
        subscription_id="sub_6", status="active", product_id="prod_pro",
        customer={"customer_id": "cust_6", "email": user["email"]},
        metadata={"user_id": user["id"], "plan": "pro"},
    ))
    _send(client, _event(
        "customer.subscription.updated", created_at="2026-07-01T00:00:00Z",
        subscription_id="sub_6", status="unpaid",
        customer={"customer_id": "cust_6", "email": user["email"]},
    ))
    assert _plan_of(app, user) == "free"


def test_failed_payment_during_dunning_does_not_revoke(client, app):
    """Retries are expected to recover; one failed charge must not cut off a
    paying customer."""
    user = make_user(app, plan="pro")
    _send(client, _event(
        "customer.subscription.created", created_at="2026-04-01T00:00:00Z",
        subscription_id="sub_7", status="active", product_id="prod_pro",
        customer={"customer_id": "cust_7", "email": user["email"]},
        metadata={"user_id": user["id"], "plan": "pro"},
    ))
    _send(client, _event(
        "invoice.payment_failed", created_at="2026-05-01T00:00:00Z", invoice_id="inv_f",
        subscription={"subscription_id": "sub_7"}, status="open", attempt_count=1,
        customer={"customer_id": "cust_7", "email": user["email"]},
    ))
    assert _plan_of(app, user) == "pro"


# ─── Out-of-order delivery ───────────────────────────────────────────────────
def test_a_stale_delete_does_not_revoke_a_resubscribed_user(client, app):
    """Deliveries can arrive reordered. A delayed cancellation from the old
    subscription must not revoke access granted by a newer event."""
    user = make_user(app, plan="free")
    _send(client, _event(
        "customer.subscription.created", created_at="2026-06-01T00:00:00Z",
        subscription_id="sub_8", status="active", product_id="prod_pro",
        customer={"customer_id": "cust_8", "email": user["email"]},
        metadata={"user_id": user["id"], "plan": "pro"},
    ))
    assert _plan_of(app, user) == "pro"

    # An OLDER cancellation turns up afterwards.
    r = _send(client, _event(
        "customer.subscription.deleted", created_at="2026-05-01T00:00:00Z",
        subscription_id="sub_8", status="canceled",
        customer={"customer_id": "cust_8", "email": user["email"]},
    ))
    assert r.status_code == 200
    assert r.get_json()["status"] == "stale"
    assert _plan_of(app, user) == "pro"       # access preserved


# ─── Transport-level behaviour ───────────────────────────────────────────────
def test_forged_signature_is_rejected_with_400(client, app):
    user = make_user(app, plan="free")
    body = json.dumps(_event(
        "checkout.completed", payment_status="paid",
        metadata={"user_id": user["id"], "plan": "business"},
    )).encode()
    ts = str(int(time.time()))
    r = client.post(WEBHOOK, data=body, headers={
        "Content-Type": "application/json",
        "X-Bachs-Signature-V2": f"t={ts},v1={'0' * 64}",
    })
    assert r.status_code == 400
    assert _plan_of(app, user) == "free"       # no access granted


def test_missing_webhook_secret_answers_503_so_bachs_retries(client, app, monkeypatch):
    monkeypatch.setattr(bachs.Config, "BACHS_WEBHOOK_SECRET", "")
    r = _send(client, _event("invoice.paid", invoice_id="i"))
    assert r.status_code == 503
    assert r.get_json()["code"] == "BILLING_UNAVAILABLE"


def test_internal_failure_answers_5xx_so_the_event_is_not_lost(client, app, monkeypatch):
    """A swallowed 200 would discard a real payment permanently."""
    def boom(*a, **k):
        raise RuntimeError("database on fire")

    monkeypatch.setattr("routes.billing_routes._target_for", boom)
    r = _send(client, _event(
        "checkout.completed", payment_status="paid", checkout_id="chk_z",
        metadata={"user_id": "whoever", "plan": "pro"},
    ))
    assert r.status_code == 500


def test_payment_amount_is_recorded_in_major_units(client, app):
    """Bachs sends "49.00" meaning forty-nine. Nothing may divide by 100."""
    user = make_user(app, plan="free")
    _send(client, _event(
        "collection.succeeded", charge_id="ch_1", checkout_id="chk_2",
        status="SUCCEEDED", amount="49.00", currency="USD",
        customer={"id": "cust_9", "email": user["email"]},
        metadata={"user_id": user["id"], "plan": "pro"},
    ))
    from models import Payment
    with app.app_context():
        payment = Payment.query.filter_by(provider_payment_id="ch_1").first()
        assert payment is not None
        assert payment.public()["amount"] == "49.00"
        assert payment.currency == "USD"
