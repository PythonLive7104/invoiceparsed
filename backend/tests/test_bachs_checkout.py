"""Checkout dispatch: Bachs takes precedence, and the guards still hold."""
import bachs
from tests.conftest import auth_header, make_user


class _Resp:
    status_code = 201
    is_success = True
    text = "{}"

    @staticmethod
    def json():
        return {"checkout_id": "chk_1", "checkout_url": "https://checkout.bachs.io/c/x"}


def _bachs_on(monkeypatch):
    monkeypatch.setattr(bachs.Config, "BACHS_SECRET_KEY", "sk_sandbox_test")
    monkeypatch.setattr(bachs.Config, "BACHS_PRODUCTS", {
        "starter": "prod_starter", "pro": "prod_pro", "business": "prod_business",
    })


def test_checkout_uses_bachs_when_configured(client, app, monkeypatch):
    _bachs_on(monkeypatch)
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, body=json)
        return _Resp()

    monkeypatch.setattr(bachs.httpx, "post", fake_post)
    user = make_user(app, plan="free")
    r = client.post("/api/billing/checkout", json={"plan": "pro"},
                    headers=auth_header(app, user))
    assert r.status_code == 200
    assert r.get_json()["url"] == "https://checkout.bachs.io/c/x"
    assert "/v1/checkout-sessions" in sent["url"]
    assert sent["body"]["product_cart"][0]["product_id"] == "prod_pro"
    # The plan must NOT be granted yet - only the webhook may do that.
    from models import Organization
    with app.app_context():
        assert Organization.query.get(user["organization_id"]).plan == "free"


def test_checkout_does_not_fall_back_to_a_free_upgrade_when_bachs_errors(client, app, monkeypatch):
    """A provider outage must surface as an error, never as a free plan."""
    _bachs_on(monkeypatch)

    def boom(*a, **k):
        raise bachs.httpx.ConnectError("down")

    monkeypatch.setattr(bachs.httpx, "post", boom)
    user = make_user(app, email="e@example.com", plan="free")
    r = client.post("/api/billing/checkout", json={"plan": "business"},
                    headers=auth_header(app, user))
    assert r.status_code == 502
    from models import Organization
    with app.app_context():
        assert Organization.query.get(user["organization_id"]).plan == "free"


def test_unpaid_upgrade_refused_while_bachs_is_configured(client, app, monkeypatch):
    """BILLING_DEMO_MODE must not override a live provider."""
    _bachs_on(monkeypatch)
    user = make_user(app, email="u@example.com", plan="free")
    r = client.post("/api/billing/upgrade", json={"plan": "business"},
                    headers=auth_header(app, user))
    assert r.status_code == 403
    assert r.get_json()["code"] == "CHECKOUT_REQUIRED"


def test_downgrade_to_free_still_bypasses_checkout(client, app, monkeypatch):
    _bachs_on(monkeypatch)
    user = make_user(app, email="f@example.com", plan="pro")
    r = client.post("/api/billing/checkout", json={"plan": "free"},
                    headers=auth_header(app, user))
    assert r.status_code == 200
    from models import Organization
    with app.app_context():
        assert Organization.query.get(user["organization_id"]).plan == "free"
