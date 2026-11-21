"""The return page, self-service reconcile, and cancellation.

These cover the paths a customer hits when a webhook is late or missing, which
is exactly when billing bugs become support tickets.
"""
from decimal import Decimal

import pytest

import bachs
from tests.conftest import auth_header, make_user


@pytest.fixture(autouse=True)
def _bachs_live(app, monkeypatch):
    # Depends on `app` deliberately: the app fixture blanks BACHS_SECRET_KEY to
    # keep the suite hermetic against a developer's .env, so this has to be set
    # up AFTER it or the blanking wins.
    monkeypatch.setattr(bachs.Config, "BACHS_SECRET_KEY", "sk_sandbox_test")
    monkeypatch.setattr(bachs.Config, "BACHS_API_BASE", "https://sandbox-api.bachs.io")
    monkeypatch.setattr(bachs.Config, "BACHS_PRODUCTS", {
        "starter": "prod_starter", "pro": "prod_pro", "business": "prod_business",
    })


def _stub_get(monkeypatch, payloads):
    """Serve canned GET responses keyed by a substring of the path."""
    calls = []

    class _Resp:
        def __init__(self, body):
            self._body = body
            self.status_code = 200
            self.is_success = True
            self.text = "{}"

        def json(self):
            return self._body

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        for fragment, body in payloads.items():
            if fragment in url:
                return _Resp(body)
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(bachs.httpx, "get", fake_get)
    return calls


def _plan_of(app, user):
    """The plan lives on the organization now."""
    from models import Organization
    with app.app_context():
        return Organization.query.get(user["organization_id"]).plan


def _add_subscription(app, user, sub_id, *, plan="pro", status="active"):
    from extensions import db
    from models import Subscription
    with app.app_context():
        row = Subscription(organization_id=user["organization_id"],
                           user_id=user["id"], provider="bachs",
                           provider_subscription_id=sub_id, plan=plan, status=status,
                           provider_customer_id="cust_1")
        db.session.add(row)
        db.session.commit()


# ─── /billing/verify ─────────────────────────────────────────────────────────
def test_verify_activates_the_plan_without_waiting_for_the_webhook(client, app, monkeypatch):
    user = make_user(app, plan="free")
    _stub_get(monkeypatch, {"/v1/checkout-sessions/chk_1": {
        "checkout_id": "chk_1", "status": "completed", "payment_status": "paid",
        "metadata": {"user_id": user["id"], "plan": "pro"},
        "customer": {"id": "cust_1", "email": user["email"]},
        "charge": {"payment_id": "pay_1", "subscription_id": "sub_1",
                   "status": "succeeded", "amount": "49.00", "currency": "USD"},
    }})
    r = client.post("/api/billing/verify", json={"checkout_id": "chk_1"},
                    headers=auth_header(app, user))
    assert r.status_code == 200
    assert r.get_json()["status"] == "success"
    assert _plan_of(app, user) == "pro"

    # The subscription mapping is recorded, so renewals resolve later.
    from models import Payment, Subscription
    with app.app_context():
        row = Subscription.query.filter_by(provider_subscription_id="sub_1").first()
        assert row is not None and row.user_id == user["id"]
        payment = Payment.query.filter_by(provider_payment_id="pay_1").first()
        assert payment.amount == Decimal("49.0000")   # major units, not 0.49


def test_verify_does_not_activate_an_unpaid_checkout(client, app, monkeypatch):
    """Reaching the return page without paying must not grant anything."""
    user = make_user(app, email="u@example.com", plan="free")
    _stub_get(monkeypatch, {"/v1/checkout-sessions/chk_2": {
        "checkout_id": "chk_2", "status": "open", "payment_status": "unpaid",
        "metadata": {"user_id": user["id"], "plan": "business"},
        "customer": {"id": "c", "email": user["email"]},
        "charge": None,
    }})
    r = client.post("/api/billing/verify", json={"checkout_id": "chk_2"},
                    headers=auth_header(app, user))
    assert r.status_code == 200
    assert r.get_json()["status"] != "success"
    assert _plan_of(app, user) == "free"


def test_verify_refuses_someone_elses_checkout(client, app, monkeypatch):
    """Otherwise a guessed or shared checkout id would upgrade the caller."""
    victim = make_user(app, email="victim@example.com", plan="business")
    attacker = make_user(app, email="attacker@example.com", plan="free")
    _stub_get(monkeypatch, {"/v1/checkout-sessions/chk_3": {
        "checkout_id": "chk_3", "status": "completed", "payment_status": "paid",
        "metadata": {"user_id": victim["id"], "plan": "business"},
        "customer": {"id": "cust_v", "email": victim["email"]},
        "charge": {"payment_id": "pay_3", "status": "succeeded",
                   "amount": "99.00", "currency": "USD"},
    }})
    r = client.post("/api/billing/verify", json={"checkout_id": "chk_3"},
                    headers=auth_header(app, attacker))
    assert r.status_code == 403
    assert _plan_of(app, attacker) == "free"


def test_verify_accepts_the_legacy_reference_key(client, app, monkeypatch):
    """An older deployed frontend still posts {reference: ...}."""
    user = make_user(app, email="legacy@example.com", plan="free")
    _stub_get(monkeypatch, {"/v1/checkout-sessions/chk_4": {
        "checkout_id": "chk_4", "payment_status": "paid",
        "metadata": {"user_id": user["id"], "plan": "starter"},
        "customer": {"id": "c", "email": user["email"]},
        "charge": {"payment_id": "pay_4", "status": "succeeded",
                   "amount": "19.00", "currency": "USD"},
    }})
    r = client.post("/api/billing/verify", json={"reference": "chk_4"},
                    headers=auth_header(app, user))
    assert r.status_code == 200
    assert _plan_of(app, user) == "starter"


# ─── /billing/sync ───────────────────────────────────────────────────────────
def test_sync_recovers_a_plan_after_a_missed_webhook(client, app, monkeypatch):
    user = make_user(app, email="sync@example.com", plan="free")
    _add_subscription(app, user, "sub_5", plan="business", status="active")
    _stub_get(monkeypatch, {"/v1/subscriptions/sub_5": {
        "id": "sub_5", "status": "active", "product": {"id": "prod_business"},
        "cancel_at_period_end": False,
    }})
    r = client.post("/api/billing/sync", headers=auth_header(app, user))
    assert r.status_code == 200
    assert _plan_of(app, user) == "business"


def test_sync_downgrades_when_the_subscription_has_ended(client, app, monkeypatch):
    """A cancelled account must not keep paid access through a missed webhook."""
    user = make_user(app, email="ended@example.com", plan="pro")
    _add_subscription(app, user, "sub_6", plan="pro", status="active")
    _stub_get(monkeypatch, {"/v1/subscriptions/sub_6": {
        "id": "sub_6", "status": "canceled", "product": {"id": "prod_pro"},
    }})
    client.post("/api/billing/sync", headers=auth_header(app, user))
    assert _plan_of(app, user) == "free"


def test_sync_does_not_downgrade_when_the_provider_is_unreachable(client, app, monkeypatch):
    """A provider outage must not cost a paying customer their plan."""
    user = make_user(app, email="outage@example.com", plan="business")
    _add_subscription(app, user, "sub_7", plan="business", status="active")

    def boom(*a, **k):
        raise bachs.httpx.ConnectError("down")

    monkeypatch.setattr(bachs.httpx, "get", boom)
    r = client.post("/api/billing/sync", headers=auth_header(app, user))
    assert r.status_code == 200
    assert _plan_of(app, user) == "business"


def test_sync_keeps_access_during_past_due(client, app, monkeypatch):
    user = make_user(app, email="dunning@example.com", plan="pro")
    _add_subscription(app, user, "sub_8", plan="pro", status="active")
    _stub_get(monkeypatch, {"/v1/subscriptions/sub_8": {
        "id": "sub_8", "status": "past_due", "product": {"id": "prod_pro"},
    }})
    client.post("/api/billing/sync", headers=auth_header(app, user))
    assert _plan_of(app, user) == "pro"


# ─── /billing/cancel ─────────────────────────────────────────────────────────
def test_cancel_schedules_at_period_end_and_keeps_access(client, app, monkeypatch):
    """The customer paid for this period, so cancelling must not take it away.
    Access ends when Bachs sends customer.subscription.deleted."""
    user = make_user(app, email="cancel@example.com", plan="pro")
    _add_subscription(app, user, "sub_9", plan="pro", status="active")
    sent = {}

    class _Resp:
        status_code = 200
        is_success = True
        text = "{}"

        @staticmethod
        def json():
            return {"id": "sub_9", "cancel_at_period_end": True}

    def fake_request(method, url, json=None, headers=None, timeout=None):
        sent.update(method=method, url=url, body=json)
        return _Resp()

    monkeypatch.setattr(bachs.httpx, "request", fake_request)
    r = client.post("/api/billing/cancel", headers=auth_header(app, user))
    assert r.status_code == 200
    assert sent["method"] == "DELETE"
    assert sent["body"] == {"cancel_at_period_end": True}
    assert r.get_json()["subscription"]["cancelAtPeriodEnd"] is True
    # Plan unchanged: still paid up until the period ends.
    assert _plan_of(app, user) == "pro"


def test_cancel_surfaces_a_provider_error(client, app, monkeypatch):
    user = make_user(app, email="cfail@example.com", plan="pro")
    _add_subscription(app, user, "sub_10", plan="pro", status="active")

    def boom(*a, **k):
        raise bachs.httpx.ConnectError("down")

    monkeypatch.setattr(bachs.httpx, "request", boom)
    r = client.post("/api/billing/cancel", headers=auth_header(app, user))
    assert r.status_code == 502
    assert _plan_of(app, user) == "pro"


def test_subscription_endpoint_exposes_the_row(client, app):
    user = make_user(app, email="sub@example.com", plan="pro")
    _add_subscription(app, user, "sub_11", plan="pro", status="active")
    r = client.get("/api/billing/subscription", headers=auth_header(app, user))
    body = r.get_json()["subscription"]
    assert body["subscriptionId"] == "sub_11"
    assert body["plan"] == "pro"
    assert body["status"] == "active"
