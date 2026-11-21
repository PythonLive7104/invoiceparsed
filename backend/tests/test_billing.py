"""Billing endpoints that are not provider-specific.

The Paystack suite this replaces is gone with the provider. What survives is the
part that matters most and is easiest to regress: what happens when NO provider
is configured. That used to grant any plan for free.
"""
import bachs
from tests.conftest import auth_header, make_user


def _no_provider(app, monkeypatch):
    monkeypatch.setattr(bachs.Config, "BACHS_SECRET_KEY", "")
    monkeypatch.setitem(app.config, "BILLING_DEMO_MODE", False)


def _demo_mode(app, monkeypatch):
    monkeypatch.setattr(bachs.Config, "BACHS_SECRET_KEY", "")
    monkeypatch.setitem(app.config, "BILLING_DEMO_MODE", True)


# ─── Demo mode (explicitly opted in) ─────────────────────────────────────────
def test_demo_upgrade_changes_plan(client, app, monkeypatch):
    _demo_mode(app, monkeypatch)
    user = make_user(app, plan="free")
    r = client.post("/api/billing/upgrade", json={"plan": "pro"},
                    headers=auth_header(app, user))
    assert r.status_code == 200
    assert r.get_json()["organization"]["plan"] == "pro"


def test_checkout_falls_back_to_demo_when_unconfigured(client, app, monkeypatch):
    _demo_mode(app, monkeypatch)
    user = make_user(app, plan="free")
    r = client.post("/api/billing/checkout", json={"plan": "starter"},
                    headers=auth_header(app, user))
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("demo") is True
    assert body["organization"]["plan"] == "starter"


def test_billing_config_reports_demo(client, app, monkeypatch):
    _demo_mode(app, monkeypatch)
    r = client.get("/api/billing/config")
    assert r.status_code == 200
    body = r.get_json()
    assert body["live"] is False
    assert body["provider"] == "bachs"


def test_invalid_plan_rejected(client, app, monkeypatch):
    _demo_mode(app, monkeypatch)
    user = make_user(app, plan="free")
    for path in ("/api/billing/upgrade", "/api/billing/checkout"):
        r = client.post(path, json={"plan": "platinum"}, headers=auth_header(app, user))
        assert r.status_code == 400, path


# ─── Fail closed when no provider is wired ───────────────────────────────────
# Removing or rotating out a provider key used to turn these endpoints into a
# free upgrade to any plan. BILLING_DEMO_MODE is now explicit, so a production
# deploy that has lost its provider refuses instead of giving the product away.
def test_upgrade_refused_when_no_provider_and_demo_off(client, app, monkeypatch):
    _no_provider(app, monkeypatch)
    user = make_user(app, plan="free")
    r = client.post("/api/billing/upgrade", json={"plan": "business"},
                    headers=auth_header(app, user))
    assert r.status_code == 503
    assert r.get_json()["code"] == "BILLING_UNAVAILABLE"

    from models import Organization
    with app.app_context():
        assert Organization.query.get(user["organization_id"]).plan == "free"


def test_checkout_refused_when_no_provider_and_demo_off(client, app, monkeypatch):
    _no_provider(app, monkeypatch)
    user = make_user(app, email="c@example.com", plan="free")
    r = client.post("/api/billing/checkout", json={"plan": "pro"},
                    headers=auth_header(app, user))
    assert r.status_code == 503
    assert r.get_json()["code"] == "BILLING_UNAVAILABLE"

    from models import Organization
    with app.app_context():
        assert Organization.query.get(user["organization_id"]).plan == "free"


def test_downgrade_to_free_still_works_without_a_provider(client, app, monkeypatch):
    """Dropping to Free costs nothing, so it must not need a payment provider —
    otherwise a billing outage would trap users on a paid plan."""
    _no_provider(app, monkeypatch)
    user = make_user(app, email="d@example.com", plan="pro")
    r = client.post("/api/billing/checkout", json={"plan": "free"},
                    headers=auth_header(app, user))
    assert r.status_code == 200

    from models import Organization
    with app.app_context():
        assert Organization.query.get(user["organization_id"]).plan == "free"


def test_webhook_answers_5xx_when_unconfigured_so_it_is_retried(client, app, monkeypatch):
    """A 4xx would make the provider DISCARD the event (Bachs does not retry a
    4xx and disables the endpoint after 72h of failures). Our own missing
    credentials must therefore read as a server fault, keeping the event queued."""
    monkeypatch.setattr(bachs.Config, "BACHS_WEBHOOK_SECRET", "")
    r = client.post("/api/billing/webhook", data=b'{"type":"invoice.paid"}',
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 503
    assert r.get_json()["code"] == "BILLING_UNAVAILABLE"


# ─── Endpoints that need a live provider ─────────────────────────────────────
def test_verify_requires_a_checkout_id(client, app, monkeypatch):
    monkeypatch.setattr(bachs.Config, "BACHS_SECRET_KEY", "sk_sandbox_x")
    user = make_user(app, email="v@example.com", plan="free")
    r = client.post("/api/billing/verify", json={}, headers=auth_header(app, user))
    assert r.status_code == 400


def test_cancel_without_a_subscription_is_404(client, app, monkeypatch):
    monkeypatch.setattr(bachs.Config, "BACHS_SECRET_KEY", "sk_sandbox_x")
    user = make_user(app, email="n@example.com", plan="pro")
    r = client.post("/api/billing/cancel", headers=auth_header(app, user))
    assert r.status_code == 404


def test_subscription_endpoint_reports_none_when_absent(client, app):
    user = make_user(app, email="s@example.com", plan="free")
    r = client.get("/api/billing/subscription", headers=auth_header(app, user))
    assert r.status_code == 200
    assert r.get_json()["subscription"] is None
