"""Tenant isolation and role enforcement.

The whole point of the organization boundary. A forgotten filter in one route is
a cross-tenant data leak that looks exactly like working code, so every
tenant-owned endpoint is probed from an account that must not see the data.

Reads, writes, deletes AND exports are all checked: an export endpoint that
leaks is just as bad as a read, and it is the one people forget.
"""
import io

import pytest

from tests.conftest import auth_header, join_org, make_org, make_user, org_header

FAKE_INVOICE = {
    "vendor": {"name": "Acme", "address": None, "email": None},
    "invoice_number": "INV-1", "invoice_date": None, "due_date": None,
    "currency": "USD", "payment_terms": None, "line_items": [],
    "subtotal": None, "tax": None, "total": 10.0,
    "confidence": {k: 1.0 for k in (
        "vendor", "invoice_number", "invoice_date", "due_date", "currency",
        "payment_terms", "line_items", "subtotal", "tax", "total")},
}


@pytest.fixture
def two_tenants(app, monkeypatch):
    """Alice and Bob, each in their own organization, with one document each."""
    import routes.extract_routes as er
    from invoice_schema import normalize
    monkeypatch.setattr(
        er, "extract_document", lambda pages, doc_type="invoice": normalize(FAKE_INVOICE)
    )
    alice = make_user(app, email="alice@example.com", plan="pro")
    bob = make_user(app, email="bob@example.com", plan="pro")
    return alice, bob


def _upload(client, app, user):
    r = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"fake-png"), "inv.png")},
        headers=auth_header(app, user),
        content_type="multipart/form-data",
    )
    assert r.status_code == 200, r.get_json()
    return r.get_json()["id"]


# ─── Documents ───────────────────────────────────────────────────────────────
def test_cannot_read_another_tenants_extraction(client, app, two_tenants):
    alice, bob = two_tenants
    eid = _upload(client, app, alice)
    r = client.get(f"/api/extractions/{eid}", headers=auth_header(app, bob))
    assert r.status_code == 404


def test_cannot_edit_another_tenants_extraction(client, app, two_tenants):
    alice, bob = two_tenants
    eid = _upload(client, app, alice)
    r = client.patch(
        f"/api/extractions/{eid}",
        json={"invoice": {"invoice_number": "HACKED"}},
        headers=auth_header(app, bob),
    )
    assert r.status_code == 404

    # And the document is untouched.
    body = client.get(f"/api/extractions/{eid}", headers=auth_header(app, alice)).get_json()
    assert body["invoice"]["invoice_number"] == "INV-1"


def test_cannot_delete_another_tenants_extraction(client, app, two_tenants):
    alice, bob = two_tenants
    eid = _upload(client, app, alice)
    assert client.delete(f"/api/extractions/{eid}", headers=auth_header(app, bob)).status_code == 404
    # Still there for its owner.
    assert client.get(f"/api/extractions/{eid}", headers=auth_header(app, alice)).status_code == 200


@pytest.mark.parametrize("path", [
    "/api/extractions/{eid}/csv",
    "/api/extractions/{eid}/xlsx",
    "/api/extractions/{eid}/files",
    "/api/extractions/{eid}/file/0",
])
def test_cannot_export_or_download_another_tenants_document(client, app, two_tenants, path):
    """Exports leak the same data a read would, and are easy to forget."""
    alice, bob = two_tenants
    eid = _upload(client, app, alice)
    r = client.get(path.format(eid=eid), headers=auth_header(app, bob))
    assert r.status_code == 404


def test_list_only_shows_your_own_organization(client, app, two_tenants):
    alice, bob = two_tenants
    _upload(client, app, alice)
    _upload(client, app, alice)
    bob_eid = _upload(client, app, bob)

    alice_rows = client.get("/api/extractions", headers=auth_header(app, alice)).get_json()
    bob_rows = client.get("/api/extractions", headers=auth_header(app, bob)).get_json()
    assert len(alice_rows["extractions"]) == 2
    assert len(bob_rows["extractions"]) == 1
    assert bob_rows["extractions"][0]["id"] == bob_eid


def test_usage_is_counted_per_organization(client, app, two_tenants):
    """A team shares one allowance, and one tenant's uploads must not consume
    another's."""
    alice, bob = two_tenants
    _upload(client, app, alice)
    _upload(client, app, alice)

    alice_usage = client.get("/api/usage", headers=auth_header(app, alice)).get_json()["usage"]
    bob_usage = client.get("/api/usage", headers=auth_header(app, bob)).get_json()["usage"]
    assert alice_usage["used"] == 2
    assert bob_usage["used"] == 0


# ─── API keys and webhooks ───────────────────────────────────────────────────
def test_cannot_revoke_another_tenants_api_key(client, app, two_tenants):
    alice, bob = two_tenants
    kid = client.post("/api/keys", json={"name": "k"},
                      headers=auth_header(app, alice)).get_json()["apiKey"]["id"]
    assert client.delete(f"/api/keys/{kid}", headers=auth_header(app, bob)).status_code == 404
    keys = client.get("/api/keys", headers=auth_header(app, bob)).get_json()["keys"]
    assert keys == []


def test_cannot_delete_or_test_another_tenants_webhook(client, app, two_tenants):
    alice, bob = two_tenants
    wid = client.post("/api/webhooks", json={"url": "https://example.com/h"},
                      headers=auth_header(app, alice)).get_json()
    # Creation may be refused by the SSRF guard resolving the host; skip if so.
    if "webhook" not in wid:
        pytest.skip("webhook creation blocked by URL validation in this environment")
    wid = wid["webhook"]["id"]
    assert client.delete(f"/api/webhooks/{wid}", headers=auth_header(app, bob)).status_code == 404
    assert client.post(f"/api/webhooks/{wid}/test", headers=auth_header(app, bob)).status_code == 404


def test_an_api_key_only_reaches_its_own_organization(client, app, two_tenants):
    """An API key belongs to one organization. Even if its owner is a member of
    another, the key must not reach that one — otherwise a key handed to a
    contractor would widen as its owner joined more teams."""
    alice, bob = two_tenants
    shared = make_org(app, bob, name="Bob and Alice", plan="pro")
    join_org(app, shared, alice, role="accountant")

    key = client.post("/api/keys", json={"name": "k"},
                      headers=auth_header(app, alice)).get_json()["key"]
    alice_eid = _upload(client, app, alice)

    # Something that belongs to the shared org, uploaded by Bob acting there.
    shared_eid = None
    r = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"fake-png"), "shared.png")},
        headers=org_header(app, bob, shared),
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    shared_eid = r.get_json()["id"]

    # The key is scoped to Alice's personal organization.
    headers = {"X-API-Key": key}
    assert client.get(f"/api/extractions/{alice_eid}", headers=headers).status_code == 200
    assert client.get(f"/api/extractions/{shared_eid}", headers=headers).status_code == 404

    # And an organization header cannot redirect it.
    assert client.get(
        f"/api/extractions/{shared_eid}",
        headers={**headers, "X-Organization-Id": shared["id"]},
    ).status_code == 404


# ─── Acting as an organization ───────────────────────────────────────────────
def test_header_selects_an_organization_you_belong_to(client, app, two_tenants):
    alice, bob = two_tenants
    shared = make_org(app, alice, name="Shared", plan="pro")

    eid = _upload(client, app, alice)  # personal
    personal_rows = client.get("/api/extractions", headers=auth_header(app, alice)).get_json()
    shared_rows = client.get("/api/extractions",
                             headers=org_header(app, alice, shared)).get_json()
    assert [r["id"] for r in personal_rows["extractions"]] == [eid]
    assert shared_rows["extractions"] == []


def test_header_naming_an_organization_you_are_not_in_is_refused(client, app, two_tenants):
    """403 rather than a silent fall back to your own organization: falling back
    would make probing someone else's id look like it worked."""
    alice, bob = two_tenants
    bobs_org = make_org(app, bob, name="Bob only", plan="pro")
    r = client.get("/api/extractions", headers=org_header(app, alice, bobs_org))
    assert r.status_code == 403
    assert r.get_json()["code"] == "NO_SUCH_ORGANIZATION"


def test_me_reports_the_acting_organization_and_memberships(client, app, two_tenants):
    alice, _bob = two_tenants
    shared = make_org(app, alice, name="Shared", plan="business")
    body = client.get("/api/auth/me", headers=org_header(app, alice, shared)).get_json()
    assert body["organization"]["id"] == shared["id"]
    assert body["organization"]["plan"] == "business"
    assert body["role"] == "owner"
    assert {o["id"] for o in body["organizations"]} == {alice["organization_id"], shared["id"]}


def test_plan_follows_the_acting_organization(client, app, two_tenants):
    """Alice is Pro personally but only Free in the shared org, so a Pro-only
    capability must be refused while acting there."""
    alice, _bob = two_tenants
    free_org = make_org(app, alice, name="Free team", plan="free")

    assert client.post("/api/keys", json={},
                       headers=auth_header(app, alice)).status_code == 200
    r = client.post("/api/keys", json={}, headers=org_header(app, alice, free_org))
    assert r.status_code == 403
    assert "Pro plan" in r.get_json()["error"]


# ─── Roles ───────────────────────────────────────────────────────────────────
def test_viewer_cannot_manage_api_keys_or_webhooks(client, app, two_tenants):
    alice, bob = two_tenants
    shared = make_org(app, alice, name="Shared", plan="pro")
    join_org(app, shared, bob, role="viewer")

    headers = org_header(app, bob, shared)
    r = client.post("/api/keys", json={"name": "k"}, headers=headers)
    assert r.status_code == 403
    assert r.get_json()["code"] == "FORBIDDEN"

    r = client.post("/api/webhooks", json={"url": "https://example.com/h"}, headers=headers)
    assert r.status_code == 403
    assert r.get_json()["code"] == "FORBIDDEN"


def test_viewer_can_still_read(client, app, two_tenants):
    """Read-only must mean read, not locked out."""
    alice, bob = two_tenants
    shared = make_org(app, alice, name="Shared", plan="pro")
    join_org(app, shared, bob, role="viewer")

    r = client.get("/api/extractions", headers=org_header(app, bob, shared))
    assert r.status_code == 200
    assert client.get("/api/keys", headers=org_header(app, bob, shared)).status_code == 200


def test_accountant_can_manage_documents_but_not_keys(client, app, two_tenants):
    alice, bob = two_tenants
    shared = make_org(app, alice, name="Shared", plan="pro")
    join_org(app, shared, bob, role="accountant")

    headers = org_header(app, bob, shared)
    r = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"fake-png"), "inv.png")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    assert client.post("/api/keys", json={}, headers=headers).status_code == 403


def test_a_members_document_belongs_to_the_organization_not_to_them(client, app, two_tenants):
    """Uploaded by one member, visible to the team — and still theirs after the
    uploader is removed from the org."""
    alice, bob = two_tenants
    shared = make_org(app, alice, name="Shared", plan="pro")
    join_org(app, shared, bob, role="accountant")

    r = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"fake-png"), "inv.png")},
        headers=org_header(app, bob, shared),
        content_type="multipart/form-data",
    )
    eid = r.get_json()["id"]

    # Alice, who did not upload it, can read it because her organization owns it.
    assert client.get(f"/api/extractions/{eid}",
                      headers=org_header(app, alice, shared)).status_code == 200
    # And it does not appear in Bob's personal organization.
    rows = client.get("/api/extractions", headers=auth_header(app, bob)).get_json()
    assert rows["extractions"] == []


# ─── The scoping helper itself ───────────────────────────────────────────────
def test_scoped_refuses_to_build_an_unscoped_query(app):
    """Fail closed: without an organization it must raise, not return every row."""
    from models import Extraction
    from tenancy import TenantError, scoped

    with app.test_request_context(), pytest.raises(TenantError):
        scoped(Extraction)


def test_webhook_dispatch_is_scoped_to_the_organization(app, two_tenants, monkeypatch):
    """A document uploaded in one organization must not notify another's
    endpoints."""
    import webhooks
    from extensions import db
    from models import Webhook

    alice, bob = two_tenants
    called = []

    monkeypatch.setattr(webhooks, "url_is_safe", lambda url: True)
    monkeypatch.setattr(webhooks, "deliver",
                        lambda hook, event, data, **kw: called.append(hook.url))

    with app.app_context():
        db.session.add(Webhook(organization_id=alice["organization_id"],
                               user_id=alice["id"], url="https://alice.example/h",
                               secret="s", active=True))
        db.session.add(Webhook(organization_id=bob["organization_id"],
                               user_id=bob["id"], url="https://bob.example/h",
                               secret="s", active=True))
        db.session.commit()

        webhooks.dispatch(app, alice["organization_id"], "extraction.completed", {})

    # dispatch runs in a thread; join it before asserting.
    import threading
    for thread in threading.enumerate():
        if thread is not threading.current_thread() and thread.daemon:
            thread.join(timeout=5)

    assert called == ["https://alice.example/h"]


def test_a_viewer_cannot_change_or_cancel_billing(client, app, two_tenants):
    """Billing spends the organization's money, so it needs billing:manage.

    This gap existed and the suite missed it: everyone is OWNER of their own
    personal organization, so a plan change always looked permitted. It only
    shows up with a low-privileged member of a SHARED organization.
    """
    alice, bob = two_tenants
    shared = make_org(app, alice, name="Shared", plan="pro")
    join_org(app, shared, bob, role="viewer")
    headers = org_header(app, bob, shared)

    for path, payload in (
        ("/api/billing/checkout", {"plan": "business"}),
        ("/api/billing/upgrade", {"plan": "business"}),
        ("/api/billing/cancel", None),
    ):
        r = client.post(path, json=payload, headers=headers)
        assert r.status_code == 403, f"{path} -> {r.status_code}"
        assert r.get_json()["code"] == "FORBIDDEN", path

    from models import Organization
    with app.app_context():
        assert Organization.query.get(shared["id"]).plan == "pro"


def test_an_accountant_cannot_change_billing_either(client, app, two_tenants):
    """The default role for an invited member must not be able to spend money."""
    alice, bob = two_tenants
    shared = make_org(app, alice, name="Shared", plan="pro")
    join_org(app, shared, bob, role="accountant")

    r = client.post("/api/billing/checkout", json={"plan": "business"},
                    headers=org_header(app, bob, shared))
    assert r.status_code == 403


def test_an_owner_can_still_manage_billing(client, app, two_tenants):
    """The gate must not lock out the person who is supposed to pay."""
    alice, _bob = two_tenants
    shared = make_org(app, alice, name="Shared", plan="pro")
    r = client.post("/api/billing/payments", headers=org_header(app, alice, shared))
    # payments is a GET; the point is the permission check passes, not the verb.
    assert r.status_code in (200, 405)
    r = client.get("/api/billing/payments", headers=org_header(app, alice, shared))
    assert r.status_code == 200


def test_every_member_can_still_see_usage(client, app, two_tenants):
    """Usage is not billing: a viewer must see how much allowance is left."""
    alice, bob = two_tenants
    shared = make_org(app, alice, name="Shared", plan="pro")
    join_org(app, shared, bob, role="viewer")
    r = client.get("/api/usage", headers=org_header(app, bob, shared))
    assert r.status_code == 200
    assert "used" in r.get_json()["usage"]
