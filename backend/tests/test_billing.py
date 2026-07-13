"""Billing: demo upgrade, checkout fallback, and Paystack webhook handling."""
import json

import billing
from tests.conftest import make_user, auth_header

SECRET = "sk_test_secret"


def test_demo_upgrade_changes_plan(client, app):
    user = make_user(app, plan="free")
    r = client.post("/api/billing/upgrade", json={"plan": "pro"}, headers=auth_header(app, user))
    assert r.status_code == 200
    assert r.get_json()["user"]["plan"] == "pro"


def test_checkout_falls_back_to_demo_when_unconfigured(client, app):
    user = make_user(app, plan="free")
    r = client.post("/api/billing/checkout", json={"plan": "starter"}, headers=auth_header(app, user))
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("demo") is True
    assert body["user"]["plan"] == "starter"


def test_billing_config_reports_demo(client):
    r = client.get("/api/billing/config")
    assert r.status_code == 200
    body = r.get_json()
    assert body["live"] is False
    assert body["provider"] == "paystack"


def test_create_checkout_calls_paystack(app, monkeypatch):
    monkeypatch.setattr(billing.Config, "PAYSTACK_SECRET_KEY", SECRET)
    monkeypatch.setenv("PAYSTACK_PLAN_PRO", "PLN_pro123")  # pinned: no provisioning
    user = make_user(app, plan="free")

    captured = {}

    class FakeResp:
        is_success = True
        status_code = 200
        text = ""
        def json(self):
            return {
                "status": True,
                "data": {"authorization_url": "https://checkout.paystack.com/abc"},
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return FakeResp()

    monkeypatch.setattr(billing.httpx, "post", fake_post)

    from models import User
    with app.app_context():
        u = User.query.get(user["id"])
        link = billing.create_checkout(u, "pro", "https://app/return")

    assert link == "https://checkout.paystack.com/abc"
    assert captured["url"].endswith("/transaction/initialize")
    assert captured["json"]["plan"] == "PLN_pro123"
    assert captured["json"]["email"] == user["email"]
    assert captured["json"]["amount"] == 4900  # $49 in cents
    assert captured["json"]["metadata"] == {"user_id": user["id"], "plan": "pro"}


# ─── Plan provisioning ───────────────────────────────────────────────────────
def _fake_paystack_plans(monkeypatch, existing, *, created=None):
    """Stub Paystack's /plan list + create. `created` collects the create payloads."""
    monkeypatch.setattr(billing.Config, "PAYSTACK_SECRET_KEY", SECRET)
    calls = {"list": 0}

    def fake_get(path, *, allow_missing=False):
        assert path.startswith("/plan")
        calls["list"] += 1
        return list(existing)

    def fake_post(path, payload):
        assert path == "/plan"
        if created is not None:
            created.append(payload)
        code = f"PLN_new_{len(existing)}"
        existing.append({**payload, "plan_code": code})
        return {"plan_code": code}

    monkeypatch.setattr(billing, "_api_get", fake_get)
    monkeypatch.setattr(billing, "_api_post", fake_post)
    return calls


def _remote_plan(name, amount, code, currency="USD", interval="monthly"):
    return {"name": name, "amount": amount, "currency": currency,
            "interval": interval, "plan_code": code}


def test_plan_code_reuses_the_existing_paystack_plan(monkeypatch):
    existing = [_remote_plan("InvoiceParsed Pro", 4900, "PLN_pro_live")]
    created = []
    calls = _fake_paystack_plans(monkeypatch, existing, created=created)

    assert billing.plan_code_for("pro") == "PLN_pro_live"
    assert created == []  # matched by name+amount+currency+interval; nothing created

    # Cached: a second lookup doesn't hit the API again.
    assert billing.plan_code_for("pro") == "PLN_pro_live"
    assert calls["list"] == 1


def test_plan_code_provisions_a_missing_plan(monkeypatch):
    created = []
    _fake_paystack_plans(monkeypatch, [], created=created)

    code = billing.plan_code_for("starter")
    assert code.startswith("PLN_")
    assert created == [{
        "name": "InvoiceParsed Starter",
        "amount": 1900,  # $19 from plans.py
        "interval": "monthly",
        "currency": "USD",
        "description": billing.get_plan("starter")["tagline"],
    }]
    # And it round-trips, so a subscription.* webhook can map the code back.
    assert billing.plan_for_code(code) == "starter"


def test_plan_code_provisions_a_new_plan_when_the_price_changed(monkeypatch):
    # A plan exists under our name but at the old price — don't sell at the old price.
    existing = [_remote_plan("InvoiceParsed Business", 8900, "PLN_biz_old")]
    created = []
    _fake_paystack_plans(monkeypatch, existing, created=created)

    code = billing.plan_code_for("business")
    assert code != "PLN_biz_old"
    assert created[0]["amount"] == 9900  # the current $99
    # Existing subscribers on the old plan still resolve to the Business tier.
    assert billing.plan_for_code("PLN_biz_old") == "business"


def test_plan_for_code_ignores_unrelated_plans(monkeypatch):
    _fake_paystack_plans(monkeypatch, [_remote_plan("Some Other Product", 500, "PLN_other")])
    assert billing.plan_for_code("PLN_other") is None
    assert billing.plan_for_code("PLN_nonexistent") is None


def test_checkout_reports_a_provisioning_failure(client, app, monkeypatch):
    monkeypatch.setattr(billing.Config, "PAYSTACK_SECRET_KEY", SECRET)

    def boom(path, *, allow_missing=False):
        raise billing.BillingError("Could not reach Paystack: timed out")

    monkeypatch.setattr(billing, "_api_get", boom)
    user = make_user(app, plan="free")

    r = client.post("/api/billing/checkout", json={"plan": "pro"}, headers=auth_header(app, user))
    assert r.status_code == 502
    assert "Paystack" in r.get_json()["error"]

    from models import User
    with app.app_context():
        assert User.query.get(user["id"]).plan == "free"  # not upgraded for free


# ─── Webhook signature verification ──────────────────────────────────────────
def _signed_request(client, event: dict, *, monkeypatch, signature=None):
    monkeypatch.setattr(billing.Config, "PAYSTACK_SECRET_KEY", SECRET)
    body = json.dumps(event).encode("utf-8")
    return client.post(
        "/api/billing/webhook",
        data=body,
        headers={
            "x-paystack-signature": signature or billing._sign(body),
            "Content-Type": "application/json",
        },
    )


def _charge_event(user, plan, reference="ref_1", **overrides):
    data = {
        "reference": reference,
        "amount": 1900,
        "currency": "USD",
        "status": "success",
        "customer": {"email": user["email"]},
        "metadata": {"user_id": user["id"], "plan": plan},
        **overrides,
    }
    return {"event": "charge.success", "data": data}


def test_webhook_activates_plan(client, app, monkeypatch):
    user = make_user(app, plan="free")
    r = _signed_request(client, _charge_event(user, "pro"), monkeypatch=monkeypatch)
    assert r.status_code == 200

    from models import User
    with app.app_context():
        assert User.query.get(user["id"]).plan == "pro"


def test_webhook_records_payment_and_history_lists_it(client, app, monkeypatch):
    user = make_user(app, plan="free")
    event = _charge_event(user, "starter", reference="ref_abc123")
    r = _signed_request(client, event, monkeypatch=monkeypatch)
    assert r.status_code == 200

    from models import User
    with app.app_context():
        assert User.query.get(user["id"]).plan == "starter"

    hist = client.get("/api/billing/payments", headers=auth_header(app, user))
    assert hist.status_code == 200
    rows = hist.get_json()["payments"]
    assert len(rows) == 1
    assert rows[0]["paymentId"] == "ref_abc123"
    assert rows[0]["amount"] == 19.0  # cents → major units
    assert rows[0]["plan"] == "starter"


def test_webhook_payment_deduplicated_on_retry(client, app, monkeypatch):
    user = make_user(app, plan="free")
    event = _charge_event(user, "starter", reference="ref_dup")
    _signed_request(client, event, monkeypatch=monkeypatch)
    _signed_request(client, event, monkeypatch=monkeypatch)  # Paystack retry

    hist = client.get("/api/billing/payments", headers=auth_header(app, user))
    assert len(hist.get_json()["payments"]) == 1


def test_webhook_subscription_create_maps_by_email_and_plan_code(client, app, monkeypatch):
    """subscription.create carries no metadata: the user comes from the customer
    email and the plan from the configured Paystack plan code."""
    monkeypatch.setenv("PAYSTACK_PLAN_BUSINESS", "PLN_biz")
    user = make_user(app, plan="free")
    event = {
        "event": "subscription.create",
        "data": {
            "subscription_code": "SUB_1",
            "status": "active",
            "customer": {"email": user["email"]},
            "plan": {"plan_code": "PLN_biz"},
        },
    }
    r = _signed_request(client, event, monkeypatch=monkeypatch)
    assert r.status_code == 200

    from models import User
    with app.app_context():
        assert User.query.get(user["id"]).plan == "business"


def test_webhook_subscription_disable_downgrades(client, app, monkeypatch):
    user = make_user(app, plan="pro")
    event = {
        "event": "subscription.disable",
        "data": {
            "subscription_code": "SUB_1",
            "status": "complete",
            "customer": {"email": user["email"]},
            "metadata": {"user_id": user["id"], "plan": "pro"},
        },
    }
    r = _signed_request(client, event, monkeypatch=monkeypatch)
    assert r.status_code == 200
    from models import User
    with app.app_context():
        assert User.query.get(user["id"]).plan == "free"


def test_webhook_bad_signature_rejected(client, app, monkeypatch):
    user = make_user(app, plan="free")
    r = _signed_request(
        client, _charge_event(user, "pro"), monkeypatch=monkeypatch, signature="deadbeef"
    )
    assert r.status_code == 400

    from models import User
    with app.app_context():
        assert User.query.get(user["id"]).plan == "free"  # unchanged


def test_webhook_missing_signature_rejected(client, app, monkeypatch):
    monkeypatch.setattr(billing.Config, "PAYSTACK_SECRET_KEY", SECRET)
    r = client.post(
        "/api/billing/webhook",
        data=json.dumps({"event": "charge.success"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400


# ─── Return-page verify ──────────────────────────────────────────────────────
def test_verify_activates_plan_from_reference(client, app, monkeypatch):
    monkeypatch.setattr(billing.Config, "PAYSTACK_SECRET_KEY", SECRET)
    user = make_user(app, plan="free")

    def fake_verify(reference):
        assert reference == "ref_return"
        return {
            "reference": "ref_return",
            "amount": 4900,
            "currency": "USD",
            "status": "success",
            "customer": {"email": user["email"]},
            "metadata": {"user_id": user["id"], "plan": "pro"},
        }

    monkeypatch.setattr(billing, "verify_transaction", fake_verify)

    r = client.post(
        "/api/billing/verify",
        json={"reference": "ref_return"},
        headers=auth_header(app, user),
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "success"
    assert body["user"]["plan"] == "pro"

    # The charge is recorded once, and the later webhook for it doesn't duplicate.
    _signed_request(
        client, _charge_event(user, "pro", reference="ref_return"), monkeypatch=monkeypatch
    )
    hist = client.get("/api/billing/payments", headers=auth_header(app, user))
    assert len(hist.get_json()["payments"]) == 1


def test_verify_rejects_another_users_reference(client, app, monkeypatch):
    monkeypatch.setattr(billing.Config, "PAYSTACK_SECRET_KEY", SECRET)
    attacker = make_user(app, email="attacker@example.com", plan="free")
    victim = make_user(app, email="victim@example.com", plan="pro")

    monkeypatch.setattr(billing, "verify_transaction", lambda ref: {
        "reference": ref,
        "amount": 4900,
        "currency": "USD",
        "status": "success",
        "customer": {"email": victim["email"]},
        "metadata": {"user_id": victim["id"], "plan": "pro"},
    })

    r = client.post(
        "/api/billing/verify",
        json={"reference": "ref_victim"},
        headers=auth_header(app, attacker),
    )
    assert r.status_code == 403

    from models import User
    with app.app_context():
        assert User.query.get(attacker["id"]).plan == "free"


# ─── Sync / reconciliation ───────────────────────────────────────────────────
def test_sync_reconciles_payments_and_plan_from_paystack(client, app, monkeypatch):
    monkeypatch.setattr(billing.Config, "PAYSTACK_SECRET_KEY", SECRET)
    user = make_user(app, plan="free")

    # Stand in for Paystack: a successful charge and an active subscription.
    def fake_fetch(u):
        assert u.id == user["id"]
        return {
            "payments": [{
                "payment_id": "ref_synced",
                "amount": 1900,
                "currency": "USD",
                "status": "success",
                "plan": "starter",
                "subscription_id": "SUB_1",
                "created_at": None,
            }],
            "active_plan": "starter",
        }

    monkeypatch.setattr(billing, "fetch_customer_billing", fake_fetch)

    r = client.post("/api/billing/sync", headers=auth_header(app, user))
    assert r.status_code == 200
    body = r.get_json()
    assert body["user"]["plan"] == "starter"  # plan activated from live subscription
    assert len(body["payments"]) == 1
    assert body["payments"][0]["paymentId"] == "ref_synced"

    # Idempotent: a second sync doesn't duplicate the row.
    r2 = client.post("/api/billing/sync", headers=auth_header(app, user))
    assert len(r2.get_json()["payments"]) == 1


def test_fetch_customer_billing_reads_subscriptions_and_transactions(app, monkeypatch):
    monkeypatch.setattr(billing.Config, "PAYSTACK_SECRET_KEY", SECRET)
    monkeypatch.setenv("PAYSTACK_PLAN_PRO", "PLN_pro123")
    user = make_user(app, plan="free")

    def fake_api_get(path, *, allow_missing=False):
        if path.startswith("/customer/"):
            return {
                "id": 77,
                "email": user["email"],
                "subscriptions": [
                    {"subscription_code": "SUB_old", "status": "cancelled",
                     "plan": {"plan_code": "PLN_pro123"}},
                    {"subscription_code": "SUB_new", "status": "active",
                     "plan": {"plan_code": "PLN_pro123"}},
                ],
            }
        assert path.startswith("/transaction?customer=77")
        return [{
            "reference": "ref_1",
            "amount": 4900,
            "currency": "USD",
            "status": "success",
            "paid_at": "2026-01-05T10:00:00.000Z",
            "metadata": {"user_id": user["id"], "plan": "pro"},
        }]

    monkeypatch.setattr(billing, "_api_get", fake_api_get)

    from models import User
    with app.app_context():
        u = User.query.get(user["id"])
        result = billing.fetch_customer_billing(u)

    assert result["active_plan"] == "pro"  # cancelled subscription ignored
    assert len(result["payments"]) == 1
    assert result["payments"][0]["payment_id"] == "ref_1"
    assert result["payments"][0]["created_at"].year == 2026


def test_fetch_customer_billing_unknown_customer(app, monkeypatch):
    monkeypatch.setattr(billing.Config, "PAYSTACK_SECRET_KEY", SECRET)
    user = make_user(app, plan="free")
    monkeypatch.setattr(billing, "_api_get", lambda path, allow_missing=False: None)

    from models import User
    with app.app_context():
        u = User.query.get(user["id"])
        assert billing.fetch_customer_billing(u) == {"payments": [], "active_plan": None}
