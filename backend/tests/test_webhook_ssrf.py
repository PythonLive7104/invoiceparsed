"""SSRF guard on customer-supplied webhook URLs.

Webhook URLs are fetched from inside our network, so a URL aimed at the Postgres
container, Redis, the API itself or the cloud metadata endpoint must be refused
at creation and again at delivery.
"""
import socket

import pytest

import webhooks
from tests.conftest import auth_header, make_user


def _public_dns(monkeypatch, address="93.184.216.34"):
    """Pretend every hostname resolves to one public address (no real DNS in tests)."""
    def fake(host, port, *a, **kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port or 80))]
    monkeypatch.setattr(webhooks.socket, "getaddrinfo", fake)


# ─── The validator ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/hook",              # the API itself / admin panel
    "http://127.0.0.1:5000/api/health",
    "http://[::1]/hook",
    "http://10.0.0.5/hook",               # our own network
    "http://172.17.0.2:5432/hook",        # the Postgres container
    "http://192.168.1.10/hook",
    "http://169.254.169.254/latest/meta-data/",  # cloud instance metadata
    "http://[::ffff:127.0.0.1]/hook",     # IPv4-mapped loopback
    "http://0.0.0.0/hook",
])
def test_private_targets_rejected(url):
    with pytest.raises(webhooks.UnsafeWebhookUrl):
        webhooks.assert_safe_url(url)
    assert webhooks.url_is_safe(url) is False


@pytest.mark.parametrize("url", [
    "ftp://example.com/hook",
    "file:///etc/passwd",
    "gopher://example.com/",
    "javascript:alert(1)",
    "",
    "not-a-url",
    "http://",
])
def test_non_http_schemes_rejected(url):
    assert webhooks.url_is_safe(url) is False


def test_overlong_url_rejected(monkeypatch):
    _public_dns(monkeypatch)
    assert webhooks.url_is_safe("https://example.com/" + "a" * 2048) is False


def test_public_host_allowed(monkeypatch):
    _public_dns(monkeypatch)
    webhooks.assert_safe_url("https://hooks.example.com/incoming")  # does not raise


def test_mixed_resolution_rejected(monkeypatch):
    """A host answering with both a public and a private record must be refused —
    otherwise which one we connect to is a coin flip."""
    def fake(host, port, *a, **kw):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443)),
        ]
    monkeypatch.setattr(webhooks.socket, "getaddrinfo", fake)
    assert webhooks.url_is_safe("https://rebind.example.com/hook") is False


def test_unresolvable_host_rejected(monkeypatch):
    def fake(host, port, *a, **kw):
        raise socket.gaierror("nope")
    monkeypatch.setattr(webhooks.socket, "getaddrinfo", fake)
    assert webhooks.url_is_safe("https://no-such-host.example/hook") is False


def test_escape_hatch_allows_private_hosts(monkeypatch):
    """Local development needs to point a webhook at its own machine."""
    monkeypatch.setattr(webhooks.Config, "WEBHOOK_ALLOW_PRIVATE_HOSTS", True)
    webhooks.assert_safe_url("http://127.0.0.1:4000/hook")  # does not raise


# ─── The endpoint ────────────────────────────────────────────────────────────
def test_create_webhook_rejects_internal_url(client, app):
    user = make_user(app, email="pro@example.com", plan="pro")
    r = client.post(
        "/api/webhooks",
        json={"url": "http://169.254.169.254/latest/meta-data/"},
        headers=auth_header(app, user),
    )
    assert r.status_code == 400
    assert r.get_json()["code"] == "INVALID_WEBHOOK_URL"

    from models import Webhook
    with app.app_context():
        assert Webhook.query.count() == 0


def test_create_webhook_accepts_public_url(client, app, monkeypatch):
    _public_dns(monkeypatch)
    user = make_user(app, email="pro2@example.com", plan="pro")
    r = client.post(
        "/api/webhooks",
        json={"url": "https://hooks.example.com/incoming"},
        headers=auth_header(app, user),
    )
    assert r.status_code == 200
    assert r.get_json()["webhook"]["url"] == "https://hooks.example.com/incoming"


# ─── Delivery-time re-check (DNS rebinding) ──────────────────────────────────
def test_delivery_blocked_when_host_rebinds_to_private(app, monkeypatch):
    """A URL that was public when accepted must still be re-checked on delivery."""
    _public_dns(monkeypatch)
    user = make_user(app, email="pro3@example.com", plan="pro")

    from extensions import db
    from models import Webhook
    with app.app_context():
        hook = Webhook(organization_id=user["organization_id"], user_id=user["id"],
                       url="https://rebind.example.com/hook", secret="s")
        db.session.add(hook)
        db.session.commit()

        # The host now answers with a loopback address, and no POST may be made.
        def private(host, port, *a, **kw):
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", port or 443))]
        monkeypatch.setattr(webhooks.socket, "getaddrinfo", private)

        def explode(*a, **kw):
            raise AssertionError("httpx.post must not be called for an unsafe URL")
        monkeypatch.setattr(webhooks.httpx, "post", explode)

        status = webhooks.deliver(hook, "ping", {}, sleep=lambda _s: None, max_attempts=1)
        assert status == 0
