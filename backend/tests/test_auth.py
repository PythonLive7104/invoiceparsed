"""Auth + email-verification flow."""
from tests.conftest import make_user


def test_register_returns_no_token_and_needs_verification(client, app):
    r = client.post("/api/auth/register", json={
        "name": "Flo", "email": "flo@example.com", "password": "password123",
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["needsVerification"] is True
    assert "token" not in body

    from models import User
    with app.app_context():
        u = User.query.filter_by(email="flo@example.com").first()
        assert u is not None and u.email_verified is False


def test_login_blocked_until_verified(client, app):
    client.post("/api/auth/register", json={
        "name": "Flo", "email": "flo@example.com", "password": "password123",
    })
    r = client.post("/api/auth/login", json={"email": "flo@example.com", "password": "password123"})
    assert r.status_code == 403
    assert r.get_json()["code"] == "email_unverified"


def test_verify_email_then_login(client, app):
    client.post("/api/auth/register", json={
        "name": "Flo", "email": "flo@example.com", "password": "password123",
    })
    from models import User
    from auth import issue_verify_token
    with app.app_context():
        u = User.query.filter_by(email="flo@example.com").first()
        token = issue_verify_token(u)

    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200
    assert "token" in r.get_json()

    r = client.post("/api/auth/login", json={"email": "flo@example.com", "password": "password123"})
    assert r.status_code == 200
    assert "token" in r.get_json()


def test_verify_email_rejects_garbage(client):
    r = client.post("/api/auth/verify-email", json={"token": "not-a-token"})
    assert r.status_code == 400


def test_wrong_password_is_401(client, app):
    make_user(app, email="real@example.com", verified=True, password="password123")
    r = client.post("/api/auth/login", json={"email": "real@example.com", "password": "nope"})
    assert r.status_code == 401


def test_password_reset_marks_verified(client, app):
    make_user(app, email="r@example.com", verified=False, password="password123")
    from models import User
    from auth import issue_reset_token
    with app.app_context():
        u = User.query.filter_by(email="r@example.com").first()
        token = issue_reset_token(u)

    r = client.post("/api/auth/reset-password", json={"token": token, "password": "newpassword1"})
    assert r.status_code == 200
    with app.app_context():
        assert User.query.filter_by(email="r@example.com").first().email_verified is True
