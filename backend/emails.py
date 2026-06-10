"""Transactional email via Resend (https://resend.com).

Uses the Resend REST API directly over httpx (no extra dependency). If
RESEND_API_KEY is not configured, sends are skipped and logged so local dev
still works without email set up.
"""
import httpx

from config import Config

RESEND_ENDPOINT = "https://api.resend.com/emails"


def _send(to: str, subject: str, html: str, reply_to: str | None = None) -> bool:
    if not Config.RESEND_API_KEY:
        print(f"[emails] RESEND_API_KEY not set — skipping email '{subject}' to {to}")
        return False
    payload = {"from": Config.RESEND_FROM, "to": [to], "subject": subject, "html": html}
    if reply_to:
        payload["reply_to"] = reply_to
    try:
        resp = httpx.post(
            RESEND_ENDPOINT,
            headers={
                "Authorization": f"Bearer {Config.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )
        if not resp.is_success:
            print(f"[emails] Resend error {resp.status_code}: {resp.text}")
        return resp.is_success
    except Exception as exc:  # noqa: BLE001
        print(f"[emails] Resend request failed: {exc}")
        return False


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace("\n", "<br>")
    )


def send_contact(name: str, email: str, message: str) -> bool:
    """Deliver a contact-form submission to the team inbox (reply-to the sender)."""
    body = f"""\
    <p style="color:#94a3b8;font-size:14px;line-height:1.6"><b>From:</b> {_escape(name)} &lt;{_escape(email)}&gt;</p>
    <p style="color:#e2e8f0;font-size:14px;line-height:1.7;white-space:pre-wrap">{_escape(message)}</p>"""
    return _send(
        Config.CONTACT_TO,
        f"InvoiceParsed contact — {name or email}",
        _layout("New contact message", body),
        reply_to=email or None,
    )


def _layout(title: str, body_html: str) -> str:
    return f"""\
<div style="background:#0b0f1a;padding:32px 0;font-family:Inter,Segoe UI,Arial,sans-serif">
  <div style="max-width:480px;margin:0 auto;background:#0f1422;border:1px solid rgba(255,255,255,0.08);border-radius:16px;overflow:hidden">
    <div style="padding:24px 28px;border-bottom:1px solid rgba(255,255,255,0.06)">
      <span style="font-size:18px;font-weight:600;color:#fff">Invoice<span style="color:#818cf8">Parsed</span></span>
    </div>
    <div style="padding:28px">
      <h1 style="margin:0 0 12px;font-size:20px;color:#fff">{title}</h1>
      {body_html}
    </div>
    <div style="padding:18px 28px;border-top:1px solid rgba(255,255,255,0.06);color:#64748b;font-size:12px">
      InvoiceParsed · AI invoice data extraction
    </div>
  </div>
</div>"""


def send_password_reset(to: str, link: str, name: str | None = None) -> bool:
    greeting = f"Hi {name}," if name else "Hi,"
    body = f"""\
    <p style="color:#94a3b8;font-size:14px;line-height:1.6">{greeting}</p>
    <p style="color:#94a3b8;font-size:14px;line-height:1.6">
      We received a request to reset your InvoiceParsed password. Click the button
      below to choose a new one. This link expires in 1 hour.
    </p>
    <p style="text-align:center;margin:28px 0">
      <a href="{link}" style="display:inline-block;background:linear-gradient(135deg,#6366f1,#a855f7);color:#fff;text-decoration:none;font-weight:600;font-size:14px;padding:12px 24px;border-radius:12px">
        Reset password
      </a>
    </p>
    <p style="color:#64748b;font-size:12px;line-height:1.6">
      If you didn't request this, you can safely ignore this email. The link below
      is for reference:<br>
      <a href="{link}" style="color:#818cf8;word-break:break-all">{link}</a>
    </p>"""
    return _send(to, "Reset your InvoiceParsed password", _layout("Reset your password", body))


def send_verification(to: str, link: str, name: str | None = None) -> bool:
    greeting = f"Hi {name}," if name else "Hi,"
    body = f"""\
    <p style="color:#94a3b8;font-size:14px;line-height:1.6">{greeting}</p>
    <p style="color:#94a3b8;font-size:14px;line-height:1.6">
      Thanks for signing up for InvoiceParsed. Confirm your email address to
      activate your account and start extracting invoices. This link expires in
      24 hours.
    </p>
    <p style="text-align:center;margin:28px 0">
      <a href="{link}" style="display:inline-block;background:linear-gradient(135deg,#6366f1,#a855f7);color:#fff;text-decoration:none;font-weight:600;font-size:14px;padding:12px 24px;border-radius:12px">
        Confirm email
      </a>
    </p>
    <p style="color:#64748b;font-size:12px;line-height:1.6">
      If you didn't create this account, you can safely ignore this email. The
      link below is for reference:<br>
      <a href="{link}" style="color:#818cf8;word-break:break-all">{link}</a>
    </p>"""
    return _send(to, "Confirm your InvoiceParsed email", _layout("Confirm your email", body))
