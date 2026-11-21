"""Bachs provider: webhook verification and event interpretation.

These are the two places a bug costs real money. A verification hole lets an
attacker grant themselves a paid plan with a forged POST; a wrong grant/revoke
mapping either strands cancelled users on paid plans or cuts off customers who
are paying.

Every expectation here is traceable to the Bachs docs rather than to a guess —
notably the lifecycle rule "remove access when you receive
customer.subscription.deleted, not when the cancellation is scheduled".
"""
import hashlib
import hmac
import json
import time
from decimal import Decimal

import pytest

import bachs

SECRET = "whsec_" + "a" * 64
OTHER_SECRET = "whsec_" + "b" * 64


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setattr(bachs.Config, "BACHS_SECRET_KEY", "sk_sandbox_test")
    monkeypatch.setattr(bachs.Config, "BACHS_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(bachs.Config, "BACHS_WEBHOOK_TOLERANCE", 300)
    monkeypatch.setattr(bachs.Config, "BACHS_API_BASE", "https://sandbox-api.bachs.io")
    monkeypatch.setattr(bachs.Config, "BACHS_PRODUCTS", {
        "starter": "prod_starter", "pro": "prod_pro", "business": "prod_business",
    })


def _sign(body: bytes, timestamp: str, secret: str = SECRET) -> str:
    return hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()


def _delivery(event: dict, *, secret=SECRET, timestamp=None, v2=True, extra_sigs=()):
    body = json.dumps(event).encode("utf-8")
    ts = timestamp or str(int(time.time()))
    sig = _sign(body, ts, secret)
    if v2:
        parts = [f"t={ts}", f"v1={sig}"] + [f"v1={s}" for s in extra_sigs]
        headers = {"X-Bachs-Signature-V2": ",".join(parts)}
    else:
        headers = {"X-Bachs-Timestamp": ts, "X-Bachs-Signature": sig}
    return headers, body


def _event(etype, **data):
    return {"id": "evt_1", "type": etype, "created_at": "2026-04-27T12:04:00Z",
            "organization_id": "acct_1", "data": data}


# ─── Signature verification ──────────────────────────────────────────────────
def test_accepts_a_valid_v2_delivery():
    headers, body = _delivery(_event("collection.succeeded", amount="29.00"))
    assert bachs.verify_webhook(headers, body)["type"] == "collection.succeeded"


def test_accepts_the_legacy_header_pair():
    headers, body = _delivery(_event("collection.succeeded"), v2=False)
    assert bachs.verify_webhook(headers, body)["type"] == "collection.succeeded"


def test_accepts_during_secret_rotation_when_any_v1_matches():
    """Bachs repeats v1= once per valid secret while a secret is rotating."""
    headers, body = _delivery(_event("invoice.paid"), extra_sigs=("deadbeef" * 8,))
    assert bachs.verify_webhook(headers, body)["type"] == "invoice.paid"


def test_rejects_a_forged_signature():
    headers, body = _delivery(_event("invoice.paid"), secret=OTHER_SECRET)
    with pytest.raises(ValueError, match="mismatch"):
        bachs.verify_webhook(headers, body)


def test_rejects_a_tampered_body():
    """The signature covers the body, so changing the amount must invalidate it."""
    headers, body = _delivery(_event("collection.succeeded", amount="29.00"))
    tampered = body.replace(b'"29.00"', b'"0.01"')
    assert tampered != body
    with pytest.raises(ValueError, match="mismatch"):
        bachs.verify_webhook(headers, tampered)


def test_rejects_a_stale_delivery():
    """Replay protection: outside the 300s window."""
    old = str(int(time.time()) - 400)
    headers, body = _delivery(_event("invoice.paid"), timestamp=old)
    with pytest.raises(ValueError, match="tolerance"):
        bachs.verify_webhook(headers, body)


def test_rejects_a_future_delivery():
    future = str(int(time.time()) + 400)
    headers, body = _delivery(_event("invoice.paid"), timestamp=future)
    with pytest.raises(ValueError, match="tolerance"):
        bachs.verify_webhook(headers, body)


def test_signature_is_computed_over_timestamp_dot_body():
    """Pin the signed string. Signing the body alone is a different scheme and
    would silently accept nothing, or worse, accept replays."""
    body = b'{"type":"x"}'
    ts = "1700000000"
    expected = hmac.new(SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    assert bachs._expected_signature(ts, body, SECRET) == expected
    # Signing only the body must NOT match.
    body_only = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert body_only != expected


@pytest.mark.parametrize("headers", [
    {},
    {"X-Bachs-Signature-V2": "garbage"},
    {"X-Bachs-Signature-V2": "t=,v1="},
    {"X-Bachs-Signature-V2": "v1=abc"},            # no timestamp
    {"X-Bachs-Signature-V2": "t=123"},             # no signature
    {"X-Bachs-Timestamp": "123"},                  # legacy, missing signature
    {"X-Bachs-Signature": "abc"},                  # legacy, missing timestamp
])
def test_rejects_malformed_or_missing_headers(headers):
    with pytest.raises(ValueError):
        bachs.verify_webhook(headers, b"{}")


def test_rejects_a_non_numeric_timestamp():
    headers = {"X-Bachs-Signature-V2": "t=not-a-time,v1=" + "a" * 64}
    with pytest.raises(ValueError, match="Unix time"):
        bachs.verify_webhook(headers, b"{}")


def test_missing_secret_is_not_a_signature_failure():
    """It must raise WebhookNotConfigured, so the route answers 5xx and Bachs
    RETRIES. A 4xx here would make Bachs discard a real payment."""
    headers, body = _delivery(_event("invoice.paid"))
    bachs.Config.BACHS_WEBHOOK_SECRET = ""
    try:
        with pytest.raises(bachs.WebhookNotConfigured):
            bachs.verify_webhook(headers, body)
    finally:
        bachs.Config.BACHS_WEBHOOK_SECRET = SECRET


def test_rejects_a_body_that_is_not_a_json_object():
    body = b'"just a string"'
    ts = str(int(time.time()))
    headers = {"X-Bachs-Signature-V2": f"t={ts},v1={_sign(body, ts)}"}
    with pytest.raises(ValueError, match="not a JSON object"):
        bachs.verify_webhook(headers, body)


# ─── Granting access ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("etype", [
    "collection.succeeded", "invoice.paid", "customer.subscription.created",
])
def test_paid_events_grant_access(etype):
    assert bachs.grants_access(_event(etype, status="active")) is True


def test_checkout_completed_grants_when_paid():
    assert bachs.grants_access(
        _event("checkout.completed", payment_status="paid", mode="subscription")
    ) is True


def test_free_checkout_does_not_grant_a_paid_plan():
    """A zero-amount checkout reports no_payment_required and must not unlock a
    paid tier."""
    assert bachs.grants_access(
        _event("checkout.completed", payment_status="no_payment_required")
    ) is False


def test_subscription_created_in_a_non_entitling_status_does_not_grant():
    assert bachs.grants_access(
        _event("customer.subscription.created", status="unpaid")
    ) is False


@pytest.mark.parametrize("etype", [
    "collection.failed", "invoice.payment_failed", "checkout.expired",
    "customer.subscription.updated", "customer.subscription.deleted",
    "payout.paid", "refund.created", "customer.created",
])
def test_other_events_do_not_grant_access(etype):
    assert bachs.grants_access(_event(etype)) is False


# ─── Revoking access ─────────────────────────────────────────────────────────
def test_subscription_deleted_revokes():
    """The documented rule: revoke on this event."""
    assert bachs.revokes_access(_event("customer.subscription.deleted",
                                       status="canceled")) is True


def test_unpaid_status_revokes():
    """Where an account set to "mark unpaid" lands once dunning is exhausted."""
    assert bachs.revokes_access(
        _event("customer.subscription.updated", status="unpaid")
    ) is True


def test_scheduled_cancellation_does_not_revoke_yet():
    """cancel_at_period_end=true with status still active means the customer has
    paid through the end of the period. Revoking here would cut off access they
    are owed; the docs say wait for customer.subscription.deleted."""
    assert bachs.revokes_access(_event(
        "customer.subscription.updated", status="active", cancel_at_period_end=True,
    )) is False


def test_past_due_does_not_revoke_during_dunning():
    """Retries are expected to recover. Cutting a paying customer off on one
    failed charge is worse than a short grace period."""
    assert bachs.revokes_access(
        _event("customer.subscription.updated", status="past_due")
    ) is False
    assert bachs.revokes_access(_event("invoice.payment_failed")) is False


def test_trialing_neither_grants_nor_revokes_wrongly():
    assert bachs.revokes_access(
        _event("customer.subscription.updated", status="trialing")
    ) is False


def test_unknown_status_leaves_access_unchanged_and_warns(caplog):
    """"paused" is in the status enum but the docs never say if it entitles."""
    with caplog.at_level("WARNING"):
        assert bachs.revokes_access(
            _event("customer.subscription.updated", status="paused",
                   subscription_id="sub_1")
        ) is False
    assert "unhandled status" in caplog.text


def test_grant_and_revoke_are_mutually_exclusive():
    """No event may both grant and revoke, or the outcome depends on call order."""
    statuses = ["trialing", "active", "past_due", "unpaid", "canceled", "paused"]
    types = sorted(bachs.ACTIVATING | bachs.DEACTIVATING | {
        "customer.subscription.updated", "collection.failed"})
    for etype in types:
        for status in statuses:
            event = _event(etype, status=status, payment_status="paid")
            assert not (bachs.grants_access(event) and bachs.revokes_access(event)), \
                f"{etype}/{status} both grants and revokes"


# ─── Reading identifiers out of the payloads ─────────────────────────────────
def test_subscription_id_from_subscription_event():
    """Subscription events use data.subscription_id, not data.id."""
    assert bachs.subscription_id_from_event(
        _event("customer.subscription.updated", subscription_id="sub_1")
    ) == "sub_1"


def test_subscription_id_from_invoice_event():
    """Invoice events nest it: data.subscription.subscription_id."""
    assert bachs.subscription_id_from_event(
        _event("invoice.paid", subscription={"subscription_id": "sub_2"})
    ) == "sub_2"


def test_subscription_id_from_checkout_event():
    assert bachs.subscription_id_from_event(
        _event("checkout.completed", subscription={"subscription_id": "sub_3"})
    ) == "sub_3"


def test_subscription_id_from_charge():
    assert bachs.subscription_id_from_event(
        _event("collection.succeeded", charge={"subscription_id": "sub_4"})
    ) == "sub_4"


def test_subscription_id_absent_is_none():
    assert bachs.subscription_id_from_event(_event("invoice.paid", subscription=None)) is None
    assert bachs.subscription_id_from_event(_event("customer.created")) is None


def test_customer_id_accepts_both_spellings():
    """Subscription events say customer_id; collection.failed says id."""
    assert bachs.customer_id_from_event(
        _event("customer.subscription.created", customer={"customer_id": "cust_1"})
    ) == "cust_1"
    assert bachs.customer_id_from_event(
        _event("collection.failed", customer={"id": "cust_2"})
    ) == "cust_2"


def test_customer_email_falls_back_to_customer_details():
    assert bachs.customer_email_from_event(
        _event("checkout.completed", customer=None,
               customer_details={"email": "a@b.com", "name": "A"})
    ) == "a@b.com"


def test_metadata_accepts_the_meta_spelling():
    """The payment object uses `meta` where everything else uses `metadata`."""
    assert bachs.metadata_from_event(
        _event("collection.succeeded", meta={"user_id": "u1"})
    ) == {"user_id": "u1"}


# ─── Mapping an event to a user and plan ─────────────────────────────────────
def test_plan_from_metadata():
    assert bachs.plan_from_event(
        _event("checkout.completed", metadata={"user_id": "u1", "plan": "pro"})
    ) == ("u1", "pro")


def test_plan_from_product_id_when_metadata_is_absent():
    """Subscription events carry product_id even when metadata is empty."""
    assert bachs.plan_from_event(
        _event("customer.subscription.created", metadata={}, product_id="prod_business")
    ) == (None, "business")


def test_plan_from_reference_fallback():
    """create_checkout encodes the organization and plan into `reference`, so an
    event carrying no metadata can still be attributed."""
    event = _event("collection.succeeded", reference="ip_org789_starter_1700000000")
    # No user id in the reference any more - the organization is what matters.
    assert bachs.plan_from_event(event) == (None, "starter")
    assert bachs.organization_id_from_event(event) == "org789"


def test_renewal_invoice_yields_neither_and_must_be_resolved_by_subscription():
    """A renewal carries no metadata or product id — this is exactly why the
    subscription id is persisted against the user."""
    event = _event("invoice.paid", invoice_id="inv_1",
                   subscription={"subscription_id": "sub_9"}, metadata={})
    assert bachs.plan_from_event(event) == (None, None)
    assert bachs.subscription_id_from_event(event) == "sub_9"


def test_an_unknown_plan_name_is_rejected():
    assert bachs.plan_from_event(
        _event("checkout.completed", metadata={"user_id": "u", "plan": "enterprise_xl"})
    ) == ("u", None)


def test_unknown_product_id_does_not_map_to_a_plan():
    assert bachs.plan_for_product("prod_not_ours") is None
    assert bachs.plan_for_product(None) is None


def test_product_lookup_round_trips():
    assert bachs.product_for("pro") == "prod_pro"
    assert bachs.plan_for_product(bachs.product_for("business")) == "business"


def test_missing_product_configuration_is_a_clear_error():
    bachs.Config.BACHS_PRODUCTS = {"starter": "", "pro": "prod_pro", "business": ""}
    with pytest.raises(bachs.BachsError, match="BACHS_PRODUCT_STARTER"):
        bachs.product_for("starter")


# ─── Amounts ─────────────────────────────────────────────────────────────────
def test_amounts_stay_major_units():
    """Bachs sends "29.00" meaning twenty-nine. Paystack sent 2900 meaning the
    same. Nothing here may divide or multiply by 100."""
    payment = bachs.payment_from_event(
        _event("collection.succeeded", amount="29.00", currency="USD",
               status="SUCCEEDED", charge_id="ch_1")
    )
    # A Decimal, not a string: it goes straight into a Numeric column, so the
    # parse happens here rather than leaving a string for the ORM to coerce.
    assert payment["amount"] == Decimal("29.00")
    assert payment["currency"] == "USD"
    assert payment["payment_id"] == "ch_1"


def test_invoice_amount_read_from_total():
    payment = bachs.payment_from_event(
        _event("invoice.paid", total="10.00", amount_paid="10.00", currency="USD",
               status="paid", invoice_id="inv_1")
    )
    assert payment["amount"] == Decimal("10.00")
    assert payment["payment_id"] == "inv_1"


def test_charge_id_from_nested_charge():
    payment = bachs.payment_from_event(
        _event("checkout.completed", charge={"id": "ch_nested"}, checkout_id="chk_1")
    )
    assert payment["payment_id"] == "ch_nested"


def test_payment_id_falls_back_to_checkout_id():
    payment = bachs.payment_from_event(_event("checkout.completed", checkout_id="chk_1"))
    assert payment["payment_id"] == "chk_1"


# ─── Creating a checkout ─────────────────────────────────────────────────────
class _User:
    id = "user123"
    email = "buyer@example.com"
    name = "Buyer"


class _Org:
    """The subscription belongs to the organization, so checkout takes one."""
    id = "org456"
    plan = "free"


class _Resp:
    def __init__(self, payload, status=201):
        self._payload = payload
        self.status_code = status
        self.is_success = 200 <= status < 300
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _capture_post(monkeypatch, payload=None, status=201):
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent["url"] = url
        sent["body"] = json
        sent["headers"] = headers
        return _Resp(payload or {"checkout_id": "chk_1",
                                 "checkout_url": "https://checkout.bachs.io/c/abc"}, status)

    monkeypatch.setattr(bachs.httpx, "post", fake_post)
    return sent


def test_create_checkout_posts_the_documented_shape(monkeypatch):
    sent = _capture_post(monkeypatch)
    url = bachs.create_checkout(_Org(), _User(), "pro", "https://invoiceparsed.com/return")

    assert url == "https://checkout.bachs.io/c/abc"
    assert sent["url"] == "https://sandbox-api.bachs.io/v1/checkout-sessions"
    body = sent["body"]
    # A recurring product, not a plan code - Bachs has no plan objects.
    assert body["product_cart"] == [{"product_id": "prod_pro", "quantity": 1}]
    # customer is REQUIRED for a recurring checkout.
    assert body["customer"]["email"] == "buyer@example.com"
    assert body["success_url"] == "https://invoiceparsed.com/return"
    # metadata is how the resulting webhook maps back. The organization is the
    # important one: it owns the plan, so a renewal must land on the right
    # tenant even if the buyer later leaves the team.
    assert body["metadata"] == {
        "organization_id": "org456", "user_id": "user123", "plan": "pro",
    }


def test_create_checkout_sends_an_idempotency_key(monkeypatch):
    """A retried request must not open two checkouts (and two subscriptions)."""
    sent = _capture_post(monkeypatch)
    bachs.create_checkout(_Org(), _User(), "pro", "https://invoiceparsed.com/return")
    assert sent["headers"]["Idempotency-Key"] == sent["body"]["reference"]
    assert sent["headers"]["Authorization"] == "Bearer sk_sandbox_test"


def test_checkout_reference_encodes_org_and_plan_and_fits_the_limit(monkeypatch):
    """`reference` must be unique per organisation and at most 128 chars, and it
    is the fallback used to map events that carry no metadata."""
    sent = _capture_post(monkeypatch)
    bachs.create_checkout(_Org(), _User(), "business", "https://invoiceparsed.com/return")
    reference = sent["body"]["reference"]
    assert len(reference) <= 128
    assert bachs._from_reference(reference) == ("org456", "business")


def test_create_checkout_refuses_the_free_plan():
    with pytest.raises(bachs.BachsError, match="not a paid plan"):
        bachs.create_checkout(_Org(), _User(), "free", "https://invoiceparsed.com/return")


def test_create_checkout_surfaces_an_api_error(monkeypatch):
    _capture_post(monkeypatch, payload={"error": "bad request"}, status=400)
    with pytest.raises(bachs.BachsError, match="400"):
        bachs.create_checkout(_Org(), _User(), "pro", "https://invoiceparsed.com/return")


def test_create_checkout_errors_when_no_url_comes_back(monkeypatch):
    _capture_post(monkeypatch, payload={"checkout_id": "chk_1"})
    with pytest.raises(bachs.BachsError, match="did not return a checkout URL"):
        bachs.create_checkout(_Org(), _User(), "pro", "https://invoiceparsed.com/return")


def test_network_failure_is_a_billing_error_not_a_crash(monkeypatch):
    def boom(*a, **k):
        raise bachs.httpx.ConnectError("no route")
    monkeypatch.setattr(bachs.httpx, "post", boom)
    with pytest.raises(bachs.BachsError, match="Could not reach Bachs"):
        bachs.create_checkout(_Org(), _User(), "pro", "https://invoiceparsed.com/return")


def test_cancel_defaults_to_end_of_period(monkeypatch):
    """Bachs' own default is IMMEDIATE cancellation, which would take away
    access the customer has already paid for - so the flag is always explicit."""
    sent = {}

    def fake_request(method, url, json=None, headers=None, timeout=None):
        sent.update(method=method, url=url, body=json)
        return _Resp({"id": "sub_1", "cancel_at_period_end": True}, 200)

    monkeypatch.setattr(bachs.httpx, "request", fake_request)
    bachs.cancel_subscription("sub_1")
    assert sent["method"] == "DELETE"
    assert sent["url"].endswith("/v1/subscriptions/sub_1")
    assert sent["body"] == {"cancel_at_period_end": True}
