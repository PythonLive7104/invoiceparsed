"""Authentication.

Two credential types are supported:
  - JWT bearer tokens for the web app (issued at login/register).
  - API keys (header `X-API-Key`, or `Authorization: Bearer ip_live_...`) for
    programmatic access on the Pro plan.

Decorators:
  - login_required          → JWT only (dashboard, account, billing).
  - api_or_login_required   → JWT or API key (extraction + read endpoints).
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

import httpx
import jwt
from flask import current_app, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import ApiKey, User
from plans import plan_allows


# ─── Passwords ─────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)


# ─── JWT ───────────────────────────────────────────────────────────────────
def issue_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "iat": now,
        "exp": now + timedelta(days=current_app.config["JWT_EXP_DAYS"]),
        "iss": "invoiceparsed",
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            current_app.config["JWT_SECRET"],
            algorithms=["HS256"],
            issuer="invoiceparsed",
        )
    except jwt.PyJWTError:
        return None


# ─── Password reset tokens ───────────────────────────────────────────────────
def _pw_fingerprint(user: User) -> str:
    """Short digest of the current password hash. Embedding it in the reset
    token makes the token single-use: once the password changes, it no longer
    matches and the link stops working."""
    return hashlib.sha256((user.password_hash or "none").encode("utf-8")).hexdigest()[:16]


def issue_reset_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "purpose": "pwreset",
        "pwv": _pw_fingerprint(user),
        "iat": now,
        "exp": now + timedelta(hours=1),
        "iss": "invoiceparsed",
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def verify_reset_token(token: str) -> User | None:
    try:
        payload = jwt.decode(
            token, current_app.config["JWT_SECRET"], algorithms=["HS256"], issuer="invoiceparsed"
        )
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != "pwreset":
        return None
    user = User.query.get(payload.get("sub"))
    if user is None or payload.get("pwv") != _pw_fingerprint(user):
        return None
    return user


# ─── Email verification tokens ───────────────────────────────────────────────
def issue_verify_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "purpose": "verify",
        "email": user.email,
        "iat": now,
        "exp": now + timedelta(hours=24),
        "iss": "invoiceparsed",
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def verify_verify_token(token: str) -> User | None:
    try:
        payload = jwt.decode(
            token, current_app.config["JWT_SECRET"], algorithms=["HS256"], issuer="invoiceparsed"
        )
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != "verify":
        return None
    user = User.query.get(payload.get("sub"))
    # Tie the token to the email it was issued for, so it can't be reused after
    # an email change.
    if user is None or payload.get("email") != user.email:
        return None
    return user


# ─── Google sign-in ──────────────────────────────────────────────────────────
def verify_google_token(credential: str) -> dict | None:
    """Verify a Google Identity Services ID token and return profile claims.

    Uses Google's tokeninfo endpoint (no extra dependencies). For high volume,
    switch to local verification with the `google-auth` library.
    """
    log = current_app.logger
    client_id = current_app.config["GOOGLE_CLIENT_ID"]
    if not client_id:
        log.warning("Google sign-in failed: backend GOOGLE_CLIENT_ID is not configured.")
        return None
    if not credential:
        log.warning("Google sign-in failed: no credential in request.")
        return None
    try:
        resp = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": credential},
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Google sign-in failed: cannot reach Google tokeninfo (%s).", exc)
        return None
    if resp.status_code != 200:
        log.warning("Google sign-in failed: tokeninfo returned %s (token invalid/expired).", resp.status_code)
        return None
    data = resp.json()
    if data.get("aud") != client_id:
        log.warning(
            "Google sign-in failed: aud mismatch. Token aud=%r but backend "
            "GOOGLE_CLIENT_ID=%r — the frontend and backend client IDs differ.",
            data.get("aud"), client_id,
        )
        return None
    if str(data.get("email_verified", "")).lower() != "true":
        log.warning("Google sign-in failed: email not verified on the Google account.")
        return None
    email = (data.get("email") or "").lower()
    if not email:
        log.warning("Google sign-in failed: token carried no email.")
        return None
    return {
        "sub": data.get("sub"),
        "email": email,
        "name": data.get("name"),
        "picture": data.get("picture"),
    }


def _user_from_jwt() -> User | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[7:].strip()
    # API keys also use the Bearer scheme — don't try to JWT-decode them.
    if token.startswith(current_app.config["API_KEY_PREFIX"]):
        return None
    payload = decode_token(token)
    if not payload:
        return None
    return User.query.get(payload.get("sub"))


# ─── API keys ──────────────────────────────────────────────────────────────
def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Return (full_key, display_prefix, key_hash). The full key is shown once."""
    full = current_app.config["API_KEY_PREFIX"] + secrets.token_urlsafe(32)
    return full, full[:12], hash_api_key(full)


def _resolve_api_key() -> tuple[User | None, ApiKey | None]:
    raw = request.headers.get("X-API-Key")
    if not raw:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[7:].strip()
            if token.startswith(current_app.config["API_KEY_PREFIX"]):
                raw = token
    if not raw:
        return None, None
    key = ApiKey.query.filter_by(key_hash=hash_api_key(raw)).first()
    if not key:
        return None, None
    return User.query.get(key.user_id), key


# ─── Decorators ──────────────────────────────────────────────────────────────
def login_required(fn):
    """Protect a route with a JWT session; attaches the user to flask.g.user."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _user_from_jwt()
        if user is None:
            return jsonify({"error": "Not authenticated."}), 401
        g.user = user
        g.auth_method = "jwt"
        return fn(*args, **kwargs)

    return wrapper


def api_or_login_required(fn):
    """Accept either a JWT session or a Pro API key."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user, key = _resolve_api_key()
        if user is not None and key is not None:
            if not plan_allows(user.plan, "api"):
                return jsonify({"error": "API access requires the Pro plan."}), 403
            key.last_used_at = datetime.utcnow()
            db.session.commit()
            g.user = user
            g.auth_method = "api"
            g.api_key = key
            return fn(*args, **kwargs)

        user = _user_from_jwt()
        if user is None:
            return jsonify({"error": "Not authenticated."}), 401
        g.user = user
        g.auth_method = "jwt"
        return fn(*args, **kwargs)

    return wrapper
