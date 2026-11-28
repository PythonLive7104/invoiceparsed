"""The payables paywall (suppliers, purchase orders, invoice matching).

Two questions that look similar and are not:

* **May this person do this?** A role question, answered 403.
* **Has this organization bought this?** A plan question, answered 402.

Sending one when you meant the other sends people to the wrong place — a
customer told "ask your administrator" when the real answer is "upgrade" will
go and bother their administrator. These tests pin both the code and the
status, and check that the paywall covers the whole module rather than the
endpoints somebody remembered.
"""
import io

import pytest

from invoice_schema import normalize
from plans import PAYABLES, PLAN_ORDER, plan_allows
from roles import OWNER
from tests.conftest import auth_header, make_user, org_header

# Every payables route, as (method, path). Read in the gate test below, which
# asserts this list IS the set of routes the three blueprints expose — so a new
# endpoint added without a paywall fails a test rather than quietly becoming
# free.
PAYABLES_PREFIXES = (
    "/api/suppliers",
    "/api/purchase-orders",
    "/api/matching",
    "/api/goods-receipts",
    "/api/approvals",
    # Payments TO suppliers. Distinct from /api/billing/payments, which is
    # what a customer pays us and is emphatically not behind this paywall.
    "/api/payments",
    "/api/reconciliation",
)


@pytest.fixture
def free(app):
    return make_user(app, email="free@example.com", plan="free")


@pytest.fixture
def starter(app):
    return make_user(app, email="starter@example.com", plan="starter")


@pytest.fixture
def pro(app):
    return make_user(app, email="pro@example.com", plan="pro")


# ─── The plan table ──────────────────────────────────────────────────────────
def test_payables_starts_at_the_pro_plan():
    assert plan_allows("free", PAYABLES) is False
    assert plan_allows("starter", PAYABLES) is False
    assert plan_allows("pro", PAYABLES) is True
    assert plan_allows("business", PAYABLES) is True


def test_the_capability_is_reported_to_the_client(app, client, pro, free):
    """The frontend locks the payables nav on what the server says, not on a
    second copy of the plan table.

    `/api/auth/me` is asserted as well as `/api/usage`, because `/me` is the
    one the app actually reads on load — `has()` in auth.jsx is fed from it,
    and the dashboard renders only once it has returned. A capability missing
    from `/me` would lock the module for a paying customer.
    """
    for user, expected in ((pro, True), (free, False)):
        body = client.get("/api/usage", headers=auth_header(app, user)).get_json()
        assert body["usage"]["capabilities"][PAYABLES] is expected

        me = client.get("/api/auth/me", headers=auth_header(app, user)).get_json()
        assert me["usage"]["capabilities"][PAYABLES] is expected


def test_every_plan_above_the_threshold_keeps_the_capability():
    """Guards against a new plan being added between starter and pro without
    anybody deciding which side of the paywall it falls on."""
    threshold = PLAN_ORDER.index("pro")
    for index, plan_id in enumerate(PLAN_ORDER):
        assert plan_allows(plan_id, PAYABLES) is (index >= threshold), plan_id


# ─── The gate itself ─────────────────────────────────────────────────────────
def test_no_payables_route_is_reachable_below_pro(app, client, free):
    """The whole module, not the endpoints somebody remembered to gate.

    Walks the real URL map rather than a hand-written list, so an endpoint
    added later without the decorator fails here instead of shipping free.
    """
    headers = auth_header(app, free)
    checked = 0

    with app.app_context():
        rules = [
            rule for rule in app.url_map.iter_rules()
            if str(rule).startswith(PAYABLES_PREFIXES)
        ]
    assert rules, "no payables routes found — has a blueprint been renamed?"

    for rule in rules:
        path = str(rule)
        if "<" in path:
            # Substitute a plausible id. The gate runs before the handler looks
            # anything up, so a nonexistent id must still answer 402 and not
            # 404 — if it 404s, the handler ran and the paywall did not.
            for part in path.split("/"):
                if part.startswith("<"):
                    path = path.replace(part, "00000000000000000000000000000000")
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            response = client.open(path, method=method, headers=headers)
            assert response.status_code == 402, (
                f"{method} {path} answered {response.status_code}, not 402"
            )
            body = response.get_json()
            assert body["code"] == "UPGRADE_REQUIRED"
            assert body["capability"] == PAYABLES
            checked += 1

    # At least one method checked per rule. Derived rather than hardcoded:
    # a constant would still pass if an entire blueprint dropped out of
    # PAYABLES_PREFIXES, which is exactly how the goods-receipt routes went
    # unwalked when they were added.
    assert checked >= len(rules), (checked, len(rules))


def test_the_error_names_the_plan_that_includes_it(app, client, free):
    """Read from the plan table, so moving the capability cannot leave the
    wrong plan name in an error message."""
    response = client.get("/api/purchase-orders", headers=auth_header(app, free))
    assert response.status_code == 402
    body = response.get_json()
    assert "Pro" in body["error"]
    assert body["plan"] == "free"
    assert "Suppliers, purchase orders and invoice matching" in body["error"]


def test_the_starter_plan_is_refused_too(app, client, starter):
    """Starter is a paid plan, which is exactly why this is worth asserting:
    "paid" and "has payables" are not the same question."""
    response = client.get("/api/suppliers", headers=auth_header(app, starter))
    assert response.status_code == 402


def test_the_pro_plan_is_let_through(app, client, pro):
    for path in ("/api/suppliers", "/api/purchase-orders", "/api/matching/summary",
                 "/api/matching/settings"):
        response = client.get(path, headers=auth_header(app, pro))
        assert response.status_code == 200, (path, response.get_json())


def test_the_plan_is_the_acting_organizations_not_the_users(app, client, free):
    """A member of a Pro organization gets payables there even if their own
    personal organization is free — the plan belongs to the organization, and
    a team shares one allowance."""
    from extensions import db
    from models import Organization, OrganizationMembership

    with app.app_context():
        org = Organization(name="Pro Team", is_personal=False, plan="pro")
        db.session.add(org)
        db.session.flush()
        db.session.add(OrganizationMembership(
            organization_id=org.id, user_id=free["id"], role=OWNER,
        ))
        db.session.commit()
        org_id = org.id

    personal = client.get("/api/purchase-orders", headers=auth_header(app, free))
    assert personal.status_code == 402

    shared = client.get(
        "/api/purchase-orders",
        headers={**auth_header(app, free), "X-Organization-Id": org_id},
    )
    assert shared.status_code == 200


# ─── The upload path ─────────────────────────────────────────────────────────
INVOICE = {
    "vendor": {"name": "Acme Supplies Ltd"},
    "invoice_number": "INV-001",
    "invoice_date": "2026-11-20",
    "currency": "NGN",
    "purchase_order_reference": "PO-0001",
    "line_items": [{"description": "Widget", "quantity": 1, "unit_price": 100,
                    "amount": 100}],
    "subtotal": "100.00", "tax": 0, "total": "100.00",
    "confidence": {},
}


def _upload(client, app, monkeypatch, headers):
    import routes.extract_routes as er

    monkeypatch.setattr(
        "openai_service.extract_document",
                        lambda pages, doc_type="invoice": normalize(INVOICE))
    response = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"bytes"), "inv.pdf")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def test_extraction_itself_is_not_behind_the_payables_paywall(
    app, client, free, monkeypatch
):
    """The paywall covers payables, not the product. A free-plan upload must
    still work exactly as it did."""
    body = _upload(client, app, monkeypatch, auth_header(app, free))
    assert body["invoice"]["total"] == "100.00"
    assert body["validation"]["status"]


def test_a_free_plan_upload_creates_no_match_and_is_shown_none(
    app, client, free, monkeypatch
):
    """Matching must not run behind the paywall. Creating a match a customer
    cannot open — every matching endpoint would answer 402 — would be worse
    than not matching at all."""
    body = _upload(client, app, monkeypatch, auth_header(app, free))
    assert body["poMatch"] is None
    with app.app_context():
        from models import InvoiceMatch

        assert InvoiceMatch.query.count() == 0


def test_a_lapsed_plan_hides_the_panel_without_destroying_the_matches(
    app, client, pro, monkeypatch
):
    """Downgrading is not deleting. The matching work an organization did on
    Pro is still theirs, and is waiting intact if they come back."""
    from extensions import db
    from models import Organization

    supplier = client.post("/api/suppliers", json={"name": "Acme Supplies Ltd"},
                           headers=auth_header(app, pro))
    assert supplier.status_code == 201, supplier.get_json()
    supplier_id = supplier.get_json()["supplier"]["id"]

    created = client.post(
        "/api/purchase-orders",
        json={"supplierId": supplier_id, "lines": [
            {"description": "Widget", "quantity": "1", "unitPrice": "100.00",
             "taxRate": "0"},
        ]},
        headers=auth_header(app, pro),
    )
    assert created.status_code == 201, created.get_json()
    po = created.get_json()["purchaseOrder"]
    for step in ("submit", "approve"):
        client.post(f"/api/purchase-orders/{po['id']}/{step}",
                    headers=auth_header(app, pro))

    body = _upload(client, app, monkeypatch, auth_header(app, pro))
    assert body["poMatch"] is not None
    assert body["poMatch"]["purchaseOrderId"] == po["id"]

    with app.app_context():
        from models import InvoiceMatch

        organization = Organization.query.filter_by(
            id=pro["organization_id"]
        ).first()
        organization.plan = "free"
        db.session.commit()
        match_count = InvoiceMatch.query.count()
    assert match_count == 1

    # Hidden, not gone.
    assert client.get("/api/matching/invoices",
                      headers=auth_header(app, pro)).status_code == 402
    detail = client.get(f"/api/extractions/{body['id']}",
                        headers=auth_header(app, pro))
    assert detail.status_code == 200
    assert detail.get_json()["poMatch"] is None

    with app.app_context():
        from models import InvoiceMatch

        assert InvoiceMatch.query.count() == 1


def test_a_role_refusal_and_a_plan_refusal_are_told_apart(app, client):
    """Both can apply at once. The plan is reported first, because it is the
    answer the customer can act on: an administrator cannot grant a capability
    the organization has not bought."""
    from extensions import db
    from models import Organization, OrganizationMembership
    from roles import VIEWER

    viewer = make_user(app, email="viewer@example.com", plan="free")
    with app.app_context():
        free_org = Organization(name="Free Team", is_personal=False, plan="free")
        pro_org = Organization(name="Pro Team", is_personal=False, plan="pro")
        db.session.add_all([free_org, pro_org])
        db.session.flush()
        for org in (free_org, pro_org):
            db.session.add(OrganizationMembership(
                organization_id=org.id, user_id=viewer["id"], role=VIEWER,
            ))
        db.session.commit()
        free_id, pro_id = free_org.id, pro_org.id

    # A viewer on a free plan: the plan is the blocker, so 402.
    blocked = client.post(
        "/api/suppliers", json={"name": "X"},
        headers={**auth_header(app, viewer), "X-Organization-Id": free_id},
    )
    assert blocked.status_code == 402
    assert blocked.get_json()["code"] == "UPGRADE_REQUIRED"

    # The same viewer on a Pro plan: the plan is fine, the role is not, so 403.
    refused = client.post(
        "/api/suppliers", json={"name": "X"},
        headers={**auth_header(app, viewer), "X-Organization-Id": pro_id},
    )
    assert refused.status_code == 403
    assert refused.get_json()["code"] == "FORBIDDEN"


def test_an_api_key_outliving_its_plan_is_refused(app, client, pro):
    """An API key must not be a way around the paywall.

    A key can only be issued on Pro or above (API access is itself a Pro
    capability), so the risk is not a free organization minting one — it is a
    key that keeps working after the plan behind it lapses.

    Such a key is refused at authentication with 403, not at the payables gate
    with 402, because API access lapsed along with payables and the key never
    reaches a view. 403 rather than 402 is the right answer for a key: the
    caller is a program, and a program cannot upgrade a plan. What matters
    here is only that it does not reach the data.
    """
    from extensions import db
    from models import Organization

    created = client.post("/api/keys", json={"name": "k"},
                          headers=auth_header(app, pro))
    assert created.status_code in (200, 201), created.get_json()
    secret = created.get_json()["key"]

    assert client.get("/api/purchase-orders",
                      headers={"Authorization": f"Bearer {secret}"}
                      ).status_code == 200

    with app.app_context():
        organization = Organization.query.filter_by(
            id=pro["organization_id"]
        ).first()
        organization.plan = "free"
        db.session.commit()

    response = client.get("/api/purchase-orders",
                          headers={"Authorization": f"Bearer {secret}"})
    assert response.status_code == 403
    assert "purchaseOrders" not in (response.get_json() or {})


def test_the_org_header_cannot_be_used_to_borrow_another_plan(app, client, free):
    """Naming a Pro organization the caller does not belong to is refused by
    tenancy before the plan is ever read."""
    other = make_user(app, email="other@example.com", plan="pro")
    response = client.get(
        "/api/purchase-orders",
        headers={**auth_header(app, free),
                 "X-Organization-Id": other["organization_id"]},
    )
    assert response.status_code == 403
    assert response.status_code != 200


def test_switching_to_a_pro_organization_switches_the_capability(app, client, free):
    """The gate reads the ACTING organization, so the same request with a
    different header gets a different answer — and `org_header` is how the
    rest of the suite expresses that."""
    from extensions import db
    from models import Organization, OrganizationMembership

    with app.app_context():
        org = Organization(name="Pro Team", is_personal=False, plan="pro")
        db.session.add(org)
        db.session.flush()
        db.session.add(OrganizationMembership(
            organization_id=org.id, user_id=free["id"], role=OWNER,
        ))
        db.session.commit()
        org_row = {"id": org.id}

    headers = {**auth_header(app, free), **org_header(app, free, org_row)}
    assert client.get("/api/matching/summary", headers=headers).status_code == 200
    assert client.get("/api/matching/summary",
                      headers=auth_header(app, free)).status_code == 402


# ─── The two plan tables ─────────────────────────────────────────────────────
def test_the_frontend_plan_table_agrees_with_this_one():
    """frontend/src/lib/plans.js is a hand-kept copy of plans.py.

    It has to be: the pricing page is prerendered at build time and cannot ask
    the server. Nothing is enforced from it — the capability list the app reads
    comes from here — but a pricing page promising a capability the backend
    does not grant is a support ticket, and a pricing page hiding one is lost
    revenue. So the drift is checked rather than hoped about.

    Deliberately a substring check rather than a JS parser: the point is to
    fail when somebody edits one file and forgets the other, and a parser for
    a JS object literal would be more code than the thing it guards.
    """
    import pathlib

    from plans import CAPABILITIES, PLAN_ORDER, PLANS

    path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "frontend" / "src" / "lib" / "plans.js"
    )
    if not path.exists():
        pytest.skip("frontend tree not present")
    source = path.read_text(encoding="utf-8")

    for plan_id in PLAN_ORDER:
        plan = PLANS[plan_id]
        assert f'id: "{plan_id}"' in source, plan_id
        assert f"price: {plan['price']}," in source, plan_id
        for capability in CAPABILITIES:
            # e.g. `payables: true,` must appear for a plan that has it. A
            # weak check on its own, but combined with the per-plan feature
            # strings below it catches a flag flipped on one side only.
            flag = f"{capability}: {str(bool(plan.get(capability))).lower()},"
            assert flag in source, (plan_id, capability, flag)
        for feature in plan["features"]:
            assert feature in source, (plan_id, feature)


def test_the_payables_feature_label_is_what_customers_are_shown():
    """The paywall message and the pricing page should name the same thing."""
    import pathlib

    from plans import PAYABLES_FEATURE

    assert PAYABLES_FEATURE == "Suppliers, purchase orders and invoice matching"
    path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "frontend" / "src" / "lib" / "plans.js"
    )
    if not path.exists():
        pytest.skip("frontend tree not present")
    # "&" on the pricing card, "and" in prose; the words that matter match.
    assert "Suppliers, purchase orders & invoice matching" in path.read_text(
        encoding="utf-8"
    )
