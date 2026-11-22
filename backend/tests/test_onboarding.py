"""Organization profile and the setup checklist.

The checklist is derived from real state on every request, never stored as a
wizard position. These tests mostly prove that: change something underneath it
and the checklist must change with it, in both directions.
"""
import io

import pytest

from extensions import db
from invoice_schema import normalize
from models import Extraction, Organization
from tests.conftest import auth_header, join_org, make_org, make_user, org_header

INVOICE = {
    "vendor": {"name": "Acme Ltd"}, "invoice_number": "INV-1",
    "invoice_date": "2026-10-15", "currency": "USD",
    "line_items": [{"description": "x", "quantity": 1, "unit_price": 10, "amount": 10}],
    "subtotal": 10, "tax": 0, "tax_percentage": 0, "total": 10, "confidence": {},
}


@pytest.fixture
def account(app):
    user = make_user(app, email="onb@example.com", plan="free")
    return user, auth_header(app, user)


def _state(client, headers):
    r = client.get("/api/organizations/current", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _steps(body):
    return {s["key"]: s for s in body["onboarding"]["steps"]}


def _upload(client, app, monkeypatch, headers):
    import routes.extract_routes as er
    monkeypatch.setattr(
        er, "extract_document", lambda pages, doc_type="invoice": normalize(INVOICE)
    )
    r = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"fake"), "inv.pdf")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert r.status_code == 200, r.get_json()
    return r.get_json()


# ─── The checklist reflects reality ──────────────────────────────────────────
def test_a_fresh_account_has_outstanding_steps(client, app, account):
    _user, headers = account
    body = _state(client, headers)
    steps = _steps(body)

    assert steps["organization"]["done"] is True   # created at sign-up
    assert steps["first_upload"]["done"] is False
    assert steps["review"]["done"] is False
    assert body["onboarding"]["complete"] is False


def test_uploading_completes_the_upload_step(client, app, account, monkeypatch):
    _user, headers = account
    assert _steps(_state(client, headers))["first_upload"]["done"] is False
    _upload(client, app, monkeypatch, headers)
    assert _steps(_state(client, headers))["first_upload"]["done"] is True


def test_reviewing_completes_the_review_step(client, app, account, monkeypatch):
    _user, headers = account
    body = _upload(client, app, monkeypatch, headers)
    assert _steps(_state(client, headers))["review"]["done"] is False

    client.patch(f"/api/extractions/{body['id']}",
                 json={"invoice": body["invoice"]}, headers=headers)
    assert _steps(_state(client, headers))["review"]["done"] is True


def test_the_checklist_goes_BACKWARDS_when_state_changes(client, app, account, monkeypatch):
    """The point of deriving it. A stored wizard position would still claim the
    step was done after the document was deleted."""
    _user, headers = account
    body = _upload(client, app, monkeypatch, headers)
    assert _steps(_state(client, headers))["first_upload"]["done"] is True

    client.delete(f"/api/extractions/{body['id']}", headers=headers)
    assert _steps(_state(client, headers))["first_upload"]["done"] is False


def test_an_unverified_email_is_an_outstanding_step(client, app):
    user = make_user(app, email="unverified@example.com", plan="free", verified=False)
    headers = auth_header(app, user)
    assert _steps(_state(client, headers))["verify_email"]["done"] is False


def test_adding_business_details_completes_the_profile_step(client, app, account):
    _user, headers = account
    assert _steps(_state(client, headers))["profile"]["done"] is False

    r = client.patch("/api/organizations/current",
                     json={"country": "NG", "currency": "NGN"}, headers=headers)
    assert r.status_code == 200
    assert _steps(r.get_json())["profile"]["done"] is True


def test_optional_steps_do_not_block_completion(client, app, account, monkeypatch):
    """Business details and plan choice are useful, not mandatory. Requiring
    them would leave the checklist permanently unfinished for someone happily
    on the free plan."""
    _user, headers = account
    body = _upload(client, app, monkeypatch, headers)
    client.patch(f"/api/extractions/{body['id']}",
                 json={"invoice": body["invoice"]}, headers=headers)

    state = _state(client, headers)["onboarding"]
    assert state["complete"] is True
    assert _steps({"onboarding": state})["profile"]["done"] is False


def test_progress_counts_only_required_steps(client, app, account):
    _user, headers = account
    state = _state(client, headers)["onboarding"]
    required = [s for s in state["steps"] if not s["optional"]]
    assert state["total"] == len(required)
    assert state["completed"] == sum(1 for s in required if s["done"])


# ─── Profile validation ──────────────────────────────────────────────────────
def test_the_organization_can_be_renamed(client, app, account):
    _user, headers = account
    r = client.patch("/api/organizations/current",
                     json={"name": "Buyer Industries"}, headers=headers)
    assert r.status_code == 200
    assert r.get_json()["organization"]["name"] == "Buyer Industries"


def test_an_empty_name_is_refused(client, app, account):
    _user, headers = account
    r = client.patch("/api/organizations/current", json={"name": "   "}, headers=headers)
    assert r.status_code == 400
    assert "name" in r.get_json()["fields"]


@pytest.mark.parametrize("value", ["US", "dollars", "U"])
def test_a_bad_currency_is_refused(client, app, account, value):
    """Storing it would quietly corrupt every report built on it later."""
    _user, headers = account
    r = client.patch("/api/organizations/current",
                     json={"currency": value}, headers=headers)
    assert r.status_code == 400
    assert "currency" in r.get_json()["fields"]


def test_a_bad_country_is_refused(client, app, account):
    _user, headers = account
    r = client.patch("/api/organizations/current",
                     json={"country": "Nigeria"}, headers=headers)
    assert r.status_code == 400


def test_codes_are_normalized_to_upper_case(client, app, account):
    _user, headers = account
    r = client.patch("/api/organizations/current",
                     json={"country": "ng", "currency": "ngn"}, headers=headers)
    org = r.get_json()["organization"]
    assert org["country"] == "NG"
    assert org["currency"] == "NGN"


def test_a_field_can_be_cleared(client, app, account):
    _user, headers = account
    client.patch("/api/organizations/current", json={"currency": "USD"}, headers=headers)
    r = client.patch("/api/organizations/current", json={"currency": ""}, headers=headers)
    assert r.get_json()["organization"]["currency"] is None


def test_omitted_fields_are_left_alone(client, app, account):
    """A partial update must not blank everything it did not mention."""
    _user, headers = account
    client.patch("/api/organizations/current",
                 json={"country": "GB", "currency": "GBP"}, headers=headers)
    r = client.patch("/api/organizations/current", json={"name": "New Name"},
                     headers=headers)
    org = r.get_json()["organization"]
    assert org["name"] == "New Name"
    assert org["country"] == "GB"
    assert org["currency"] == "GBP"


# ─── Dismissal ───────────────────────────────────────────────────────────────
def test_the_checklist_can_be_dismissed_and_restored(client, app, account):
    _user, headers = account
    assert _state(client, headers)["onboarding"]["dismissed"] is False

    r = client.post("/api/organizations/current/onboarding/dismiss", headers=headers)
    assert r.get_json()["onboarding"]["dismissed"] is True
    assert _state(client, headers)["onboarding"]["dismissed"] is True

    r = client.post("/api/organizations/current/onboarding/restore", headers=headers)
    assert r.get_json()["onboarding"]["dismissed"] is False


def test_dismissing_does_not_fake_the_steps(client, app, account):
    """Hiding the checklist must not claim the work was done."""
    _user, headers = account
    client.post("/api/organizations/current/onboarding/dismiss", headers=headers)
    state = _state(client, headers)["onboarding"]
    assert state["dismissed"] is True
    assert state["complete"] is False


# ─── Permissions and isolation ───────────────────────────────────────────────
def test_only_an_admin_can_change_organization_settings(client, app, account):
    owner, _headers = account
    member = make_user(app, email="member@example.com", plan="pro")
    shared = make_org(app, owner, name="Shared", plan="pro")
    join_org(app, shared, member, role="accountant")

    r = client.patch("/api/organizations/current", json={"name": "Hijacked"},
                     headers=org_header(app, member, shared))
    assert r.status_code == 403
    assert r.get_json()["code"] == "FORBIDDEN"

    with app.app_context():
        assert Organization.query.get(shared["id"]).name == "Shared"


def test_a_member_can_still_read_the_checklist(client, app, account):
    owner, _headers = account
    member = make_user(app, email="reader@example.com", plan="pro")
    shared = make_org(app, owner, name="Shared", plan="pro")
    join_org(app, shared, member, role="viewer")

    r = client.get("/api/organizations/current", headers=org_header(app, member, shared))
    assert r.status_code == 200
    assert r.get_json()["organization"]["id"] == shared["id"]


def test_the_checklist_counts_only_this_organizations_documents(client, app, monkeypatch):
    alice = make_user(app, email="ao@example.com", plan="pro")
    bob = make_user(app, email="bo@example.com", plan="pro")
    _upload(client, app, monkeypatch, auth_header(app, alice))

    steps = _steps(_state(client, auth_header(app, bob)))
    assert steps["first_upload"]["done"] is False


def test_the_endpoint_reports_the_acting_organization(client, app, account):
    owner, headers = account
    shared = make_org(app, owner, name="Second Org", plan="pro")
    body = _state(client, org_header(app, owner, shared))
    assert body["organization"]["name"] == "Second Org"
    assert body["role"] == "owner"
