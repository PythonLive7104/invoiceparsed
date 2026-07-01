"""Transactional & professional email via Resend (https://resend.com).

Uses the Resend REST API directly over httpx (no extra dependency). If
RESEND_API_KEY is not configured, sends are skipped and logged so local dev
still works without email set up.

Layout: every message is wrapped in a shared branded shell (`_layout`) so the
individual templates below only describe their own body. The small `_button`,
`_para` and `_muted` helpers keep those bodies to a few lines each and give all
emails a consistent look.
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


# ─── Presentation helpers ────────────────────────────────────────────────────
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


def _para(text: str, color: str = "#94a3b8") -> str:
    """A body paragraph. `text` is treated as raw HTML — callers escape as needed."""
    return f'<p style="color:{color};font-size:14px;line-height:1.7;margin:0 0 12px">{text}</p>'


def _muted(text: str) -> str:
    return f'<p style="color:#64748b;font-size:12px;line-height:1.6;margin:16px 0 0">{text}</p>'


def _button(link: str, label: str) -> str:
    return f"""\
<p style="text-align:center;margin:28px 0">
  <a href="{link}" style="display:inline-block;background:linear-gradient(135deg,#6366f1,#a855f7);color:#fff;text-decoration:none;font-weight:600;font-size:14px;padding:12px 24px;border-radius:12px">
    {label}
  </a>
</p>"""


def _greeting(name: str | None) -> str:
    return f"Hi {_escape(name)}," if name else "Hi,"


# ─── Transactional templates ─────────────────────────────────────────────────
def send_contact(name: str, email: str, message: str) -> bool:
    """Deliver a contact-form submission to the team inbox (reply-to the sender)."""
    body = (
        _para(f"<b>From:</b> {_escape(name)} &lt;{_escape(email)}&gt;")
        + _para(_escape(message), color="#e2e8f0")
    )
    return _send(
        Config.CONTACT_TO,
        f"InvoiceParsed contact — {name or email}",
        _layout("New contact message", body),
        reply_to=email or None,
    )


def send_password_reset(to: str, link: str, name: str | None = None) -> bool:
    body = (
        _para(_greeting(name))
        + _para(
            "We received a request to reset your InvoiceParsed password. Click the "
            "button below to choose a new one. This link expires in 1 hour."
        )
        + _button(link, "Reset password")
        + _muted(
            "If you didn't request this, you can safely ignore this email. The link "
            f'below is for reference:<br><a href="{link}" style="color:#818cf8;word-break:break-all">{link}</a>'
        )
    )
    return _send(to, "Reset your InvoiceParsed password", _layout("Reset your password", body))


def send_verification(to: str, link: str, name: str | None = None) -> bool:
    body = (
        _para(_greeting(name))
        + _para(
            "Thanks for signing up for InvoiceParsed. Confirm your email address to "
            "activate your account and start extracting invoices. This link expires "
            "in 24 hours."
        )
        + _button(link, "Confirm email")
        + _muted(
            "If you didn't create this account, you can safely ignore this email. The "
            f'link below is for reference:<br><a href="{link}" style="color:#818cf8;word-break:break-all">{link}</a>'
        )
    )
    return _send(to, "Confirm your InvoiceParsed email", _layout("Confirm your email", body))


def send_welcome(to: str, name: str | None = None) -> bool:
    """Warm onboarding email, sent once an account's email is confirmed."""
    dashboard = f'{Config.APP_URL.rstrip("/")}/dashboard'
    body = (
        _para(_greeting(name))
        + _para(
            "Your email is confirmed and your account is ready. InvoiceParsed turns "
            "invoices, receipts and bank statements into clean, structured data in "
            "seconds — upload a document and we'll do the rest."
        )
        + _para("Here's how to get the most out of it:")
        + _para(
            "• Upload a PDF or image to extract line items, totals and vendor details<br>"
            "• Export results to CSV or Excel for your accounting tools<br>"
            "• Generate an API key to automate extraction from your own apps",
            color="#cbd5e1",
        )
        + _button(dashboard, "Open your dashboard")
        + _muted("Questions? Just reply to this email — we read every message.")
    )
    return _send(to, "Welcome to InvoiceParsed 🎉", _layout("Welcome aboard", body))


def send_plan_changed(to: str, plan: str, name: str | None = None) -> bool:
    """Confirmation that a subscription plan changed (upgrade or downgrade)."""
    plan_label = (plan or "free").capitalize()
    dashboard = f'{Config.APP_URL.rstrip("/")}/dashboard'
    if plan and plan != "free":
        message = (
            f"Your InvoiceParsed plan is now <b style=\"color:#fff\">{plan_label}</b>. "
            "The new limits and features are active on your account right away — thanks "
            "for upgrading!"
        )
    else:
        message = (
            "Your InvoiceParsed subscription has been moved to the "
            f"<b style=\"color:#fff\">{plan_label}</b> plan. You can upgrade again any "
            "time from your dashboard."
        )
    body = (
        _para(_greeting(name))
        + _para(message)
        + _button(dashboard, "View your plan")
        + _muted("You can review your billing history and manage your plan from the dashboard.")
    )
    return _send(to, f"Your plan is now {plan_label}", _layout("Plan updated", body))


def send_payment_receipt(
    to: str,
    amount,
    currency: str | None,
    plan: str | None,
    payment_id: str | None = None,
    name: str | None = None,
) -> bool:
    """Receipt for a successful payment. `amount` is in major units (e.g. dollars)."""
    cur = (currency or "USD").upper()
    amount_str = f"{amount:.2f}" if isinstance(amount, (int, float)) else str(amount or "—")
    plan_label = (plan or "").capitalize() or "your subscription"
    rows = [
        ("Plan", plan_label),
        ("Amount", f"{amount_str} {cur}"),
    ]
    if payment_id:
        rows.append(("Payment ID", _escape(payment_id)))
    table = "".join(
        f'<tr><td style="padding:6px 0;color:#64748b;font-size:13px">{label}</td>'
        f'<td style="padding:6px 0;color:#e2e8f0;font-size:13px;text-align:right">{value}</td></tr>'
        for label, value in rows
    )
    body = (
        _para(_greeting(name))
        + _para("Thanks for your payment. Here's your receipt:")
        + f'<table style="width:100%;border-collapse:collapse;margin:8px 0 4px;'
          f'border-top:1px solid rgba(255,255,255,0.06);border-bottom:1px solid rgba(255,255,255,0.06)">{table}</table>'
        + _muted("Keep this email for your records. Need an invoice? Just reply and we'll send one.")
    )
    return _send(to, f"Your InvoiceParsed receipt — {amount_str} {cur}", _layout("Payment receipt", body))


def send_custom(to: str, subject: str, heading: str, body_html: str, reply_to: str | None = None) -> bool:
    """Send an admin-composed message, wrapped in the branded layout.

    `body_html` is trusted HTML supplied by an admin (see the admin composer),
    not user input, so it is inserted verbatim.
    """
    return _send(to, subject, _layout(heading, body_html), reply_to=reply_to)


def text_to_html(text: str) -> str:
    """Turn a plain-text admin message into safe, paragraph-formatted body HTML.

    Blank lines separate paragraphs; single newlines become line breaks. Escapes
    the content so admins can paste plain text without worrying about markup.
    """
    blocks = [b for b in (text or "").replace("\r\n", "\n").split("\n\n")]
    return "".join(_para(_escape(block)) for block in blocks if block.strip())


# Templates offered to the admin "send to selected users" bulk action. Each entry
# is (label, sender) where sender is called as sender(email, name).
BULK_TEMPLATES = {
    "welcome": ("Welcome email", lambda email, name: send_welcome(email, name)),
}
