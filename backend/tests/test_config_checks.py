"""Startup configuration checks.

Each of these corresponds to a misconfiguration that actually reached
production and whose only symptom was somewhere far from the cause.
"""
import config_checks


class _Cfg:
    """Minimal stand-in; the checker only reads attributes."""
    RESEND_API_KEY = ""
    RESEND_FROM = ""
    BACHS_SECRET_KEY = ""
    BACHS_API_BASE = "https://api.bachs.io"
    BILLING_DEMO_MODE = False
    JWT_SECRET = "a-real-secret"
    APP_URL = "https://invoiceparsed.com"


def _cfg(**overrides):
    cfg = _Cfg()
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _joined(cfg):
    return " ".join(config_checks.check(cfg))


def test_clean_production_config_warns_about_nothing():
    assert config_checks.check(_cfg(RESEND_API_KEY="re_x",
                                    RESEND_FROM="App <noreply@invoiceparsed.com>")) == []


def test_local_dev_is_not_nagged():
    """No live service configured means this is a laptop; localhost is correct."""
    assert config_checks.check(_cfg(APP_URL="http://localhost:5173",
                                    JWT_SECRET="change-me")) == []


def test_localhost_app_url_in_production_warns():
    """This put a localhost link in a real password-reset email."""
    warnings = _joined(_cfg(RESEND_API_KEY="re_x", APP_URL="http://localhost:5173"))
    assert "APP_URL" in warnings and "localhost" in warnings


def test_sandbox_sender_warns():
    """This silently blocked every password reset and signup confirmation."""
    warnings = _joined(_cfg(RESEND_API_KEY="re_x",
                            RESEND_FROM="App <onboarding@resend.dev>"))
    assert "sandbox" in warnings


def test_default_jwt_secret_in_production_warns():
    warnings = _joined(_cfg(RESEND_API_KEY="re_x", JWT_SECRET="change-me"))
    assert "JWT_SECRET" in warnings


def test_live_key_against_sandbox_base_warns():
    warnings = _joined(_cfg(BACHS_SECRET_KEY="sk_live_x",
                            BACHS_API_BASE="https://sandbox-api.bachs.io"))
    assert "401" in warnings


def test_sandbox_key_against_sandbox_base_is_fine():
    assert config_checks.check(_cfg(BACHS_SECRET_KEY="sk_sandbox_x",
                                    BACHS_API_BASE="https://sandbox-api.bachs.io")) == []


def test_demo_billing_with_a_live_provider_warns():
    warnings = _joined(_cfg(BACHS_SECRET_KEY="sk_live_x", BILLING_DEMO_MODE=True))
    assert "BILLING_DEMO_MODE" in warnings


def test_checks_are_logged_not_just_returned(caplog):
    with caplog.at_level("WARNING"):
        config_checks.check(_cfg(RESEND_API_KEY="re_x", APP_URL="http://localhost:5173"))
    assert "[config]" in caplog.text
