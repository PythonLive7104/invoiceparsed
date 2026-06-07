"""Webhook signing + retry/backoff."""
import hashlib
import hmac

import webhooks
from tests.conftest import make_user


def test_sign_is_hmac_sha256():
    body = b'{"hello":"world"}'
    expected = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert webhooks.sign("secret", body) == expected


def test_backoff_grows_then_caps(app):
    with app.app_context():
        # base=2 → 2, 4, 8, ... capped at WEBHOOK_BACKOFF_CAP
        assert webhooks._backoff_delay(1) == 2
        assert webhooks._backoff_delay(2) == 4
        assert webhooks._backoff_delay(10) <= webhooks.Config.WEBHOOK_BACKOFF_CAP


def _make_webhook(app, user):
    from extensions import db
    from models import Webhook
    with app.app_context():
        w = Webhook(user_id=user["id"], url="https://example.com/hook", secret="shh", active=True)
        db.session.add(w)
        db.session.commit()
        return w.id


def test_deliver_retries_until_success(app, monkeypatch):
    user = make_user(app)
    wid = _make_webhook(app, user)

    statuses = iter([0, 500, 200])  # fail, fail, succeed
    attempts = {"n": 0}

    def fake_attempt(webhook, event, body, delivery_id, attempt):
        attempts["n"] += 1
        return next(statuses)

    sleeps = []
    monkeypatch.setattr(webhooks, "_attempt", fake_attempt)

    from models import Webhook
    with app.app_context():
        w = Webhook.query.get(wid)
        status = webhooks.deliver(w, "extraction.completed", {"id": "x"}, sleep=sleeps.append)
        assert status == 200
        assert attempts["n"] == 3
        assert sleeps == [2, 4]  # slept before retry 2 and 3, not after success
        assert Webhook.query.get(wid).last_status == 200


def test_deliver_gives_up_after_max_attempts(app, monkeypatch):
    user = make_user(app, email="g@example.com")
    wid = _make_webhook(app, user)

    monkeypatch.setattr(webhooks, "_attempt", lambda *a, **k: 500)
    sleeps = []

    from models import Webhook
    with app.app_context():
        w = Webhook.query.get(wid)
        status = webhooks.deliver(w, "extraction.completed", {"id": "x"}, sleep=sleeps.append)
        assert status == 500
        # 4 attempts total → slept 3 times between them.
        assert len(sleeps) == webhooks.Config.WEBHOOK_MAX_ATTEMPTS - 1
        assert Webhook.query.get(wid).last_status == 500
