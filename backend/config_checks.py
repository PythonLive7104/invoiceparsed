"""Startup configuration sanity checks.

These exist because of a specific, repeated failure mode: a setting that is
perfectly correct for local development silently breaks production, and the
only symptom appears somewhere far away — a 403 buried in container logs, or a
password-reset link pointing at localhost in a customer's inbox.

Every check WARNS rather than failing. A wrong value should be loud at boot, but
refusing to start would turn a cosmetic misconfiguration into an outage, and
these heuristics can be wrong.

The signal for "this looks like production" is that a real external service is
configured. Nobody wires a live Resend or Bachs key into a laptop by accident.
"""
import logging

logger = logging.getLogger(__name__)

LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "[::1]")
SANDBOX_EMAIL_SENDER = "resend.dev"


def looks_like_production(config) -> bool:
    """True when a live external service is configured."""
    return bool(
        getattr(config, "RESEND_API_KEY", "")
        or getattr(config, "BACHS_SECRET_KEY", "")
    )


def check(config) -> list[str]:
    """Return a list of configuration warnings. Also logs each one."""
    warnings: list[str] = []
    production = looks_like_production(config)

    app_url = (getattr(config, "APP_URL", "") or "").strip()
    if production and any(host in app_url for host in LOCAL_HOSTS):
        warnings.append(
            f"APP_URL is {app_url!r}, which points at this machine. Every link "
            f"emailed to a customer (password reset, email confirmation) is "
            f"built from it, and so is the checkout return URL — which Bachs "
            f"refuses outright for a local address. Set APP_URL to your public "
            f"https:// URL."
        )

    sender = (getattr(config, "RESEND_FROM", "") or "").strip()
    if getattr(config, "RESEND_API_KEY", "") and SANDBOX_EMAIL_SENDER in sender:
        warnings.append(
            f"RESEND_FROM is {sender!r}, Resend's shared sandbox sender. It is "
            f"accepted by the API but refused with a 403 for every recipient "
            f"except the account owner, so no real user receives anything. Set "
            f"it to an address on a domain you have verified."
        )

    secret = getattr(config, "JWT_SECRET", "")
    if production and secret in ("", "change-me"):
        warnings.append(
            "JWT_SECRET is still the default. Anyone who knows it can mint a "
            "session for any account. Generate one with: "
            "python -c \"import secrets;print(secrets.token_urlsafe(48))\""
        )

    if (
        getattr(config, "BACHS_SECRET_KEY", "").startswith("sk_live_")
        and "sandbox" in (getattr(config, "BACHS_API_BASE", "") or "")
    ):
        warnings.append(
            "BACHS_SECRET_KEY is a live key but BACHS_API_BASE points at the "
            "sandbox. A key only works against its own environment, so every "
            "billing call will return 401."
        )

    if getattr(config, "BILLING_DEMO_MODE", False) and production:
        warnings.append(
            "BILLING_DEMO_MODE is on while a live provider is configured. Plan "
            "changes would be granted without payment if the provider key were "
            "ever removed."
        )

    for warning in warnings:
        logger.warning("[config] %s", warning)
    return warnings
