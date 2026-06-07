"""Auth endpoints: register, login, me, Google sign-in, password reset, account."""
import os
import re
import shutil

from flask import Blueprint, current_app, g, jsonify, redirect, request

from config import Config

from auth import (
    hash_password,
    issue_reset_token,
    issue_token,
    issue_verify_token,
    login_required,
    verify_google_token,
    verify_password,
    verify_reset_token,
    verify_verify_token,
)
from emails import send_password_reset, send_verification
from extensions import db, limiter
from models import Extraction, User
from plans import build_usage, start_of_month

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Per-IP throttle for credential / email-sending endpoints (brute-force + spam).
auth_limit = limiter.limit(lambda: current_app.config["RATELIMIT_AUTH"])


def _send_verification(user: User) -> None:
    token = issue_verify_token(user)
    link = f'{current_app.config["APP_URL"].rstrip("/")}/verify-email?token={token}'
    send_verification(user.email, link, user.name)


def _count_usage(user: User) -> int:
    return (
        Extraction.query.filter(
            Extraction.user_id == user.id,
            Extraction.status == "completed",
            Extraction.created_at >= start_of_month(),
        ).count()
    )


@auth_bp.post("/register")
@auth_limit
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip() or None

    if not EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with that email already exists."}), 409

    user = User(
        email=email,
        name=name,
        password_hash=hash_password(password),
        plan="free",
        email_verified=False,
    )
    db.session.add(user)
    db.session.commit()

    # No session yet — the user must confirm their email first. Don't return a token.
    _send_verification(user)
    return jsonify({"user": user.public(), "needsVerification": True})


@auth_bp.post("/login")
@auth_limit
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if user and not user.password_hash:
        return jsonify({"error": 'This account uses Google sign-in. Click "Continue with Google".'}), 400
    if user is None or not verify_password(password, user.password_hash):
        return jsonify({"error": "Invalid email or password."}), 401
    if not user.email_verified:
        # Credentials are correct but the email is unconfirmed — re-send the link
        # and withhold the session until they confirm.
        _send_verification(user)
        return jsonify({
            "error": "Please confirm your email to continue. We've sent you a new link.",
            "code": "email_unverified",
        }), 403

    return jsonify({"user": user.public(), "token": issue_token(user)})


def _upsert_google_user(info: dict) -> User:
    """Find the user behind a verified Google profile, linking by google_sub or
    email, creating a new free account if neither exists."""
    user = User.query.filter_by(google_sub=info["sub"]).first()
    if user is None:
        # Link to an existing email account, or create a new one.
        user = User.query.filter_by(email=info["email"]).first()
        if user:
            user.google_sub = info["sub"]
            if not user.image:
                user.image = info.get("picture")
        else:
            user = User(
                email=info["email"],
                name=info.get("name"),
                google_sub=info["sub"],
                image=info.get("picture"),
                plan="free",
            )
            db.session.add(user)
    # Google has already verified ownership of the email address.
    user.email_verified = True
    db.session.commit()
    return user


@auth_bp.post("/google")
@auth_limit
def google_auth():
    """Popup/JS flow: the frontend posts the ID token as JSON and gets a JWT back."""
    data = request.get_json(silent=True) or {}
    info = verify_google_token(data.get("credential"))
    if info is None:
        return jsonify({"error": "Google sign-in failed. Please try again."}), 401

    user = _upsert_google_user(info)
    return jsonify({"user": user.public(), "token": issue_token(user)})


@auth_bp.post("/google/callback")
@auth_limit
def google_callback():
    """Redirect flow (GIS ux_mode="redirect"). Google submits a top-level form
    POST here with the ID token and a CSRF token. We verify the double-submit
    cookie, exchange the credential for a session, then bounce the browser back
    to the SPA with the JWT in the URL fragment (kept out of server logs)."""
    app_url = current_app.config["APP_URL"].rstrip("/")

    # Double-submit cookie check, per Google's redirect-mode guidance. The
    # signed ID token (verified below) is the real authenticity guarantee; this
    # only mitigates login-CSRF. Skip when the cookie is absent — it isn't sent
    # when the SPA and API live on different subdomains.
    cookie_csrf = request.cookies.get("g_csrf_token")
    body_csrf = request.form.get("g_csrf_token")
    if cookie_csrf and body_csrf and cookie_csrf != body_csrf:
        return redirect(f"{app_url}/login?error=google")

    info = verify_google_token(request.form.get("credential"))
    if info is None:
        return redirect(f"{app_url}/login?error=google")

    user = _upsert_google_user(info)
    token = issue_token(user)
    return redirect(f"{app_url}/auth/google#token={token}")


@auth_bp.post("/forgot-password")
@auth_limit
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    user = User.query.filter_by(email=email).first()
    # Only email users with a local password can reset; Google-only accounts skip.
    if user and user.password_hash:
        token = issue_reset_token(user)
        link = f'{current_app.config["APP_URL"].rstrip("/")}/reset-password?token={token}'
        send_password_reset(user.email, link, user.name)

    # Always respond the same way — don't reveal whether the email is registered.
    return jsonify({"success": True})


@auth_bp.post("/reset-password")
@auth_limit
def reset_password():
    data = request.get_json(silent=True) or {}
    token = data.get("token") or ""
    password = data.get("password") or ""

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    user = verify_reset_token(token)
    if user is None:
        return jsonify({"error": "This reset link is invalid or has expired."}), 400

    user.password_hash = hash_password(password)
    # Completing a reset proves they control the inbox, so treat it as verified.
    user.email_verified = True
    db.session.commit()

    # Log them straight in.
    return jsonify({"user": user.public(), "token": issue_token(user)})


@auth_bp.post("/verify-email")
@auth_limit
def verify_email():
    """Confirm an email/password account from the emailed link, then sign in."""
    data = request.get_json(silent=True) or {}
    user = verify_verify_token(data.get("token") or "")
    if user is None:
        return jsonify({"error": "This confirmation link is invalid or has expired."}), 400

    if not user.email_verified:
        user.email_verified = True
        db.session.commit()

    return jsonify({"user": user.public(), "token": issue_token(user)})


@auth_bp.post("/resend-verification")
@auth_limit
def resend_verification():
    """Re-send the confirmation email. Always responds the same way so it doesn't
    reveal whether an address is registered."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    user = User.query.filter_by(email=email).first()
    if user and user.password_hash and not user.email_verified:
        _send_verification(user)

    return jsonify({"success": True})


@auth_bp.get("/me")
@login_required
def me():
    user = g.user
    usage = build_usage(_count_usage(user), user.plan)
    return jsonify({"user": user.public(), "usage": usage})


# ─── Account settings ────────────────────────────────────────────────────────
@auth_bp.patch("/profile")
@login_required
def update_profile():
    """Update editable profile fields (currently the display name)."""
    data = request.get_json(silent=True) or {}
    g.user.name = (data.get("name") or "").strip() or None
    db.session.commit()
    return jsonify({"user": g.user.public()})


@auth_bp.post("/change-password")
@login_required
def change_password():
    """Change the account password. Requires the current password when one is
    already set; Google-only accounts can set one without a current password."""
    data = request.get_json(silent=True) or {}
    new = data.get("newPassword") or ""
    if len(new) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    user = g.user
    if user.password_hash and not verify_password(data.get("currentPassword") or "", user.password_hash):
        return jsonify({"error": "Your current password is incorrect."}), 400

    user.password_hash = hash_password(new)
    db.session.commit()
    return jsonify({"success": True})


@auth_bp.delete("/account")
@login_required
def delete_account():
    """Permanently delete the account and all its data (extractions, API keys,
    webhooks via cascade) plus stored upload files."""
    user = g.user
    # Remove stored original files for each extraction before the rows cascade.
    for ext in Extraction.query.filter_by(user_id=user.id).all():
        shutil.rmtree(os.path.join(Config.UPLOAD_DIR, ext.id), ignore_errors=True)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"success": True})
