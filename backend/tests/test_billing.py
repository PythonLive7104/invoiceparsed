"""Billing: demo upgrade, checkout fallback, and Dodo webhook handling."""
import base64
import json
import time

import billing
from tests.conftest import make_user, auth_header


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
    assert r.get_json()["live"] is False


def test_create_checkout_calls_dodo(app, monkeypatch):
    monkeypatch.setattr(billing.Config, "DODO_API_KEY", "test-key")
    monkeypatch.setenv("DODO_PRODUCT_PRO", "prod_pro_123")
    user = make_user(app, plan="free")

    captured = {}

    class FakeResp:
        is_success = True
        status_code = 200
        text = ""
        def json(self):
            return {"payment_link": "https://checkout.dodopayments.test/abc"}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return FakeResp()

    monkeypatch.setattr(billing.httpx, "post", fake_post)

    from models import User
    with app.app_context():
        u = User.query.get(user["id"])
        link = billing.create_checkout(u, "pro", "https://app/return")

    assert link == "https://checkout.dodopayments.test/abc"
    assert captured["json"]["product_id"] == "prod_pro_123"
    assert captured["json"]["metadata"] == {"user_id": user["id"], "plan": "pro"}


# ─── Webhook signature verification ──────────────────────────────────────────
def _signed_request(client, app, secret_b64, event: dict, *, monkeypatch, ts=None):
    monkeypatch.setattr(billing.Config, "DODO_WEBHOOK_SECRET", secret_b64)
    body = json.dumps(event).encode("utf-8")
    msg_id = "msg_1"
    timestamp = str(ts or int(time.time()))
    sig = billing._sign(msg_id, timestamp, body)
    return client.post(
        "/api/billing/webhook",
        data=body,
        headers={
            "webhook-id": msg_id,
            "webhook-timestamp": timestamp,
            "webhook-signature": f"v1,{sig}",
            "Content-Type": "application/json",
        },
    )


def test_webhook_activates_plan(client, app, monkeypatch):
    secret = base64.b64encode(b"super-secret").decode()
    user = make_user(app, plan="free")
    event = {
        "type": "subscription.active",
        "data": {"metadata": {"user_id": user["id"], "plan": "pro"}},
    }
    r = _signed_request(client, app, secret, event, monkeypatch=monkeypatch)
    assert r.status_code == 200

    from models import User
    with app.app_context():
        assert User.query.get(user["id"]).plan == "pro"


def test_webhook_records_payment_and_history_lists_it(client, app, monkeypatch):
    secret = base64.b64encode(b"super-secret").decode()
    user = make_user(app, plan="free")
    event = {
        "type": "payment.succeeded",
        "data": {
            "metadata": {"user_id": user["id"], "plan": "starter"},
            "payment_id": "pay_abc123",
            "subscription_id": "sub_xyz",
            "total_amount": 1900,
            "currency": "USD",
            "status": "succeeded",
        },
    }
    r = _signed_request(client, app, secret, event, monkeypatch=monkeypatch)
    assert r.status_code == 200

    # Plan activated and a payment row recorded.
    from models import User
    with app.app_context():
        assert User.query.get(user["id"]).plan == "starter"

    hist = client.get("/api/billing/payments", headers=auth_header(app, user))
    assert hist.status_code == 200
    rows = hist.get_json()["payments"]
    assert len(rows) == 1
    assert rows[0]["paymentId"] == "pay_abc123"
    assert rows[0]["amount"] == 19.0  # cents → major units
    assert rows[0]["plan"] == "starter"


def test_webhook_payment_deduplicated_on_retry(client, app, monkeypatch):
    secret = base64.b64encode(b"super-secret").decode()
    user = make_user(app, plan="free")
    event = {
        "type": "payment.succeeded",
        "data": {
            "metadata": {"user_id": user["id"], "plan": "starter"},
            "payment_id": "pay_dup",
            "total_amount": 1900,
            "currency": "USD",
            "status": "succeeded",
        },
    }
    _signed_request(client, app, secret, event, monkeypatch=monkeypatch)
    _signed_request(client, app, secret, event, monkeypatch=monkeypatch)  # Dodo retry

    hist = client.get("/api/billing/payments", headers=auth_header(app, user))
    assert len(hist.get_json()["payments"]) == 1


def test_webhook_cancellation_downgrades(client, app, monkeypatch):
    secret = base64.b64encode(b"super-secret").decode()
    user = make_user(app, plan="pro")
    event = {
        "type": "subscription.cancelled",
        "data": {"metadata": {"user_id": user["id"], "plan": "pro"}},
    }
    r = _signed_request(client, app, secret, event, monkeypatch=monkeypatch)
    assert r.status_code == 200
    from models import User
    with app.app_context():
        assert User.query.get(user["id"]).plan == "free"


def test_webhook_bad_signature_rejected(client, app, monkeypatch):
    monkeypatch.setattr(billing.Config, "DODO_WEBHOOK_SECRET", base64.b64encode(b"s").decode())
    body = json.dumps({"type": "subscription.active"}).encode()
    r = client.post(
        "/api/billing/webhook",
        data=body,
        headers={
            "webhook-id": "msg_1",
            "webhook-timestamp": str(int(time.time())),
            "webhook-signature": "v1,wrongsignature",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 400


def test_webhook_stale_timestamp_rejected(client, app, monkeypatch):
    secret = base64.b64encode(b"super-secret").decode()
    user = make_user(app, plan="free")
    event = {"type": "subscription.active", "data": {"metadata": {"user_id": user["id"], "plan": "pro"}}}
    old = int(time.time()) - 9999
    r = _signed_request(client, app, secret, event, monkeypatch=monkeypatch, ts=old)
    assert r.status_code == 400
