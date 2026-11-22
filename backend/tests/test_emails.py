"""Email rendering, with a focus on money.

Receipts state an amount a customer will compare against their card statement,
so the formatting is worth pinning. These tests send nothing: _send() returns
False with no network call when RESEND_API_KEY is empty, which conftest ensures.
"""
from decimal import Decimal

import pytest

import emails


@pytest.mark.parametrize("amount,expected", [
    (Decimal("49.0000"), "49.00"),   # what the Numeric column hands back
    (Decimal("19.99"), "19.99"),
    (Decimal("1234.5"), "1234.50"),
    (Decimal("0.00"), "0.00"),       # a real zero, not "missing"
    (49, "49.00"),
    (49.0, "49.00"),
    ("19.99", "19.99"),
])
def test_receipt_amount_is_two_places(amount, expected, monkeypatch):
    """A Decimal is not an int or a float, so an isinstance check on those two
    rendered "49.0000" on a customer receipt."""
    captured = {}

    def fake_send(to, subject, html, reply_to=None):
        captured["html"] = html
        captured["subject"] = subject
        return True

    monkeypatch.setattr(emails, "_send", fake_send)
    assert emails.send_payment_receipt("a@b.com", amount, "USD", "pro", "pay_1") is True
    assert f"{expected} USD" in captured["html"], captured["html"]


def test_receipt_handles_a_missing_amount(monkeypatch):
    monkeypatch.setattr(emails, "_send", lambda *a, **k: True)
    assert emails.send_payment_receipt("a@b.com", None, "USD", "pro") is True


def test_send_is_skipped_without_a_key(capsys):
    """Local dev must work with no email configured, and say so."""
    emails.Config.RESEND_API_KEY = ""
    assert emails._send("a@b.com", "subj", "<p>x</p>") is False
    assert "skipping email" in capsys.readouterr().out


def test_warns_when_left_on_the_sandbox_sender(capsys, monkeypatch):
    """The sandbox sender is accepted by the API but refused for every real
    recipient, so a deploy left on it looks configured and delivers nothing.
    That is exactly what broke password resets in production."""
    monkeypatch.setattr(emails.Config, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(emails.Config, "RESEND_FROM", "App <onboarding@resend.dev>")
    monkeypatch.setattr(emails.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("network blocked in tests")))

    emails._send("someone@example.com", "subj", "<p>x</p>")
    out = capsys.readouterr().out
    assert "sandbox sender" in out
    assert "verified domain" in out


def test_no_warning_on_a_verified_sender(capsys, monkeypatch):
    monkeypatch.setattr(emails.Config, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(emails.Config, "RESEND_FROM", "App <noreply@example.com>")
    monkeypatch.setattr(emails.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("network blocked in tests")))

    emails._send("someone@example.com", "subj", "<p>x</p>")
    assert "sandbox sender" not in capsys.readouterr().out
