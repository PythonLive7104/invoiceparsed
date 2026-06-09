"""API key + webhook management endpoints (Pro-gated)."""
from tests.conftest import make_user, auth_header


# ─── API keys ────────────────────────────────────────────────────────────────
def test_free_user_cannot_create_key(client, app):
    user = make_user(app, plan="free")
    r = client.post("/api/keys", json={"name": "k"}, headers=auth_header(app, user))
    assert r.status_code == 403


def test_pro_key_lifecycle(client, app):
    user = make_user(app, email="pro@example.com", plan="pro")
    h = auth_header(app, user)
    # Create — full key returned exactly once, with ip_live_ prefix.
    r = client.post("/api/keys", json={"name": "CI"}, headers=h)
    assert r.status_code == 200
    body = r.get_json()
    assert body["key"].startswith("ip_live_")
    kid = body["apiKey"]["id"]
    # List shows it (no plaintext key).
    lst = client.get("/api/keys", headers=h).get_json()["keys"]
    assert any(k["id"] == kid for k in lst)
    assert "key" not in lst[0]
    # Revoke.
    assert client.delete(f"/api/keys/{kid}", headers=h).status_code == 200
    assert client.delete(f"/api/keys/{kid}", headers=h).status_code == 404  # gone


def test_api_key_authenticates_extraction(client, app, monkeypatch):
    import routes.extract_routes as er
    monkeypatch.setattr(er, "extract_document", lambda pages, doc_type="invoice": {
        "vendor": {"name": "X", "address": None, "email": None}, "invoice_number": None,
        "invoice_date": None, "due_date": None, "currency": "USD", "payment_terms": None,
        "line_items": [], "subtotal": None, "tax": None, "total": 1.0,
        "confidence": {k: 1.0 for k in ("vendor", "invoice_number", "invoice_date", "due_date",
            "currency", "payment_terms", "line_items", "subtotal", "tax", "total")},
    })
    user = make_user(app, email="apiuser@example.com", plan="pro")
    full = client.post("/api/keys", json={}, headers=auth_header(app, user)).get_json()["key"]
    # Use the API key (not JWT) to hit an extraction endpoint.
    r = client.get("/api/extractions", headers={"X-API-Key": full})
    assert r.status_code == 200


# ─── Webhooks ────────────────────────────────────────────────────────────────
def test_free_user_cannot_create_webhook(client, app):
    user = make_user(app, plan="free")
    r = client.post("/api/webhooks", json={"url": "https://x.com/h"}, headers=auth_header(app, user))
    assert r.status_code == 403


def test_webhook_crud_and_validation(client, app):
    user = make_user(app, email="w@example.com", plan="pro")
    h = auth_header(app, user)
    assert client.post("/api/webhooks", json={"url": "not-a-url"}, headers=h).status_code == 400
    r = client.post("/api/webhooks", json={"url": "https://example.com/hook"}, headers=h)
    assert r.status_code == 200
    hook = r.get_json()["webhook"]
    assert hook["secret"].startswith("whsec_")
    wid = hook["id"]
    assert client.delete(f"/api/webhooks/{wid}", headers=h).status_code == 200


def test_webhook_test_endpoint_single_attempt(client, app, monkeypatch):
    import webhooks
    calls = {"n": 0}

    def fake_attempt(*a, **k):
        calls["n"] += 1
        return 0  # simulate failure

    monkeypatch.setattr(webhooks, "_attempt", fake_attempt)
    user = make_user(app, email="wt@example.com", plan="pro")
    h = auth_header(app, user)
    wid = client.post("/api/webhooks", json={"url": "https://example.com/hook"}, headers=h).get_json()["webhook"]["id"]
    r = client.post(f"/api/webhooks/{wid}/test", headers=h)
    assert r.status_code == 200
    assert r.get_json()["delivered"] is False
    assert calls["n"] == 1  # single attempt, no retry/backoff blocking
