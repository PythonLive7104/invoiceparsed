"""Approval workflows (P2.5).

Weighted toward the ways an authorization control fails quietly:

* a rule that matches when it should not, or silently matches nothing;
* a chain that can be short-circuited by approving the document directly;
* somebody approving their own submission;
* a request parked forever because nobody is left who can sign it;
* a delegation that outlives the holiday it was created for.

Every fixture runs on the **Pro** plan: payables is a Pro capability, and
below it every endpoint here answers 402.
"""
from decimal import Decimal

import pytest

from roles import (
    ACCOUNTANT,
    ADMIN,
    APPROVER,
    FINANCE_MANAGER,
    PROCUREMENT,
    VIEWER,
)
from tests.conftest import auth_header, join_org, make_org, make_user, org_header


# ─── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture
def org(app):
    """A real multi-member organization: workflows are meaningless alone."""
    owner = make_user(app, email="owner@example.com", plan="pro")
    shared = make_org(app, owner, name="Acme", plan="pro")
    people = {"owner": owner}
    for key, email, role in (
        ("buyer", "buyer@example.com", PROCUREMENT),
        ("manager", "manager@example.com", FINANCE_MANAGER),
        ("director", "director@example.com", ADMIN),
        ("approver", "approver@example.com", APPROVER),
        ("clerk", "clerk@example.com", ACCOUNTANT),
    ):
        user = make_user(app, email=email, plan="pro")
        join_org(app, shared, user, role)
        people[key] = user
    return {"org": shared, "people": people}


def headers_for(app, org, who):
    user = org["people"][who]
    return {**auth_header(app, user), **org_header(app, user, org["org"])}


@pytest.fixture
def supplier(app, org):
    from extensions import db
    from models import Supplier
    from suppliers import match_key_for

    with app.app_context():
        row = Supplier(
            organization_id=org["org"]["id"],
            name="Acme Supplies Ltd",
            match_key=match_key_for("Acme Supplies Ltd"),
            currency="NGN",
        )
        db.session.add(row)
        db.session.commit()
        return {"id": row.id, "name": row.name}


def make_rule(client, headers, **overrides):
    body = {
        "name": "Everything needs one approval",
        "subjectType": "purchase_order",
        "steps": [{"level": 1, "approverType": "role",
                   "approverRole": FINANCE_MANAGER}],
    }
    body.update(overrides)
    response = client.post("/api/approvals/rules", json=body, headers=headers)
    return response


LINE = {"description": "Widget", "quantity": "10", "unitPrice": "100.00",
        "taxRate": "0"}


def create_po(client, headers, supplier_id, lines=None, **extra):
    body = {"supplierId": supplier_id, "lines": lines or [LINE]}
    body.update(extra)
    response = client.post("/api/purchase-orders", json=body, headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["purchaseOrder"]


def submit(client, headers, po_id):
    return client.post(f"/api/purchase-orders/{po_id}/submit", headers=headers)


def open_request(client, headers, po_id):
    body = client.get(f"/api/purchase-orders/{po_id}", headers=headers).get_json()
    return body.get("approval")


def request_detail(client, headers, request_id):
    return client.get(f"/api/approvals/requests/{request_id}",
                      headers=headers).get_json()["approvalRequest"]


# ─── Rule matching ───────────────────────────────────────────────────────────
def test_a_rule_with_no_conditions_matches_everything(app, client, org, supplier):
    headers = headers_for(app, org, "owner")
    assert make_rule(client, headers).status_code == 201

    po = create_po(client, headers_for(app, org, "buyer"), supplier["id"])
    submit(client, headers_for(app, org, "buyer"), po["id"])

    live = open_request(client, headers, po["id"])
    assert live is not None
    assert live["ruleName"] == "Everything needs one approval"


def test_an_amount_threshold_only_catches_orders_above_it(
    app, client, org, supplier
):
    headers = headers_for(app, org, "owner")
    make_rule(client, headers, name="Big spend", minAmount="5000")

    buyer = headers_for(app, org, "buyer")
    small = create_po(client, buyer, supplier["id"])              # 1,000.00
    submit(client, buyer, small["id"])
    assert open_request(client, headers, small["id"]) is None

    big = create_po(client, buyer, supplier["id"],
                    lines=[{**LINE, "quantity": "100"}])          # 10,000.00
    submit(client, buyer, big["id"])
    assert open_request(client, headers, big["id"]) is not None


def test_the_threshold_boundary_is_inclusive(app, client, org, supplier):
    """An order of exactly the threshold needs approval. Off-by-one here is
    the difference between a control and a rounding error."""
    headers = headers_for(app, org, "owner")
    make_rule(client, headers, name="At or above 1000", minAmount="1000")

    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])                 # exactly 1,000
    submit(client, buyer, po["id"])
    assert open_request(client, headers, po["id"]) is not None


def test_an_unreadable_amount_fails_a_threshold_rather_than_passing_it(app, org):
    """An order whose total cannot be read must not slip under a threshold
    and skip approval."""
    with app.app_context():
        from approvals import rule_matches
        from models import ApprovalRule

        rule = ApprovalRule(organization_id=org["org"]["id"], name="x",
                            min_amount=Decimal("100"))
        assert rule_matches(rule, {"amount": None}) is False
        assert rule_matches(rule, {"amount": "150"}) is True


def test_conditions_are_anded_not_ored(app, client, org, supplier):
    headers = headers_for(app, org, "owner")
    make_rule(client, headers, name="Big ops spend",
              minAmount="5000", department="Operations")

    buyer = headers_for(app, org, "buyer")
    # Big enough, wrong department.
    wrong = create_po(client, buyer, supplier["id"],
                      lines=[{**LINE, "quantity": "100"}], department="Marketing")
    submit(client, buyer, wrong["id"])
    assert open_request(client, headers, wrong["id"]) is None

    # Right department, too small.
    small = create_po(client, buyer, supplier["id"], department="Operations")
    submit(client, buyer, small["id"])
    assert open_request(client, headers, small["id"]) is None

    # Both.
    both = create_po(client, buyer, supplier["id"],
                     lines=[{**LINE, "quantity": "100"}], department="Operations")
    submit(client, buyer, both["id"])
    assert open_request(client, headers, both["id"]) is not None


def test_text_conditions_ignore_case_and_whitespace(app, client, org, supplier):
    headers = headers_for(app, org, "owner")
    make_rule(client, headers, name="Ops", department="operations")

    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"], department="  Operations  ")
    submit(client, buyer, po["id"])
    assert open_request(client, headers, po["id"]) is not None


def test_only_the_highest_priority_matching_rule_applies(
    app, client, org, supplier
):
    """Combining every match would produce chains nobody can explain."""
    headers = headers_for(app, org, "owner")
    make_rule(client, headers, name="Low", priority=1,
              steps=[{"level": 1, "approverType": "role",
                      "approverRole": APPROVER}])
    make_rule(client, headers, name="High", priority=10,
              steps=[{"level": 1, "approverType": "role",
                      "approverRole": FINANCE_MANAGER}])

    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])

    live = open_request(client, headers, po["id"])
    assert live["ruleName"] == "High"
    assert {step["approverRole"] for step in live["steps"]} == {FINANCE_MANAGER}


def test_an_inactive_rule_does_not_apply(app, client, org, supplier):
    headers = headers_for(app, org, "owner")
    created = make_rule(client, headers).get_json()["rule"]
    client.delete(f"/api/approvals/rules/{created['id']}", headers=headers)

    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    assert open_request(client, headers, po["id"]) is None


def test_a_supplier_specific_rule_only_catches_that_supplier(
    app, client, org, supplier
):
    from extensions import db
    from models import Supplier
    from suppliers import match_key_for

    headers = headers_for(app, org, "owner")
    with app.app_context():
        other = Supplier(organization_id=org["org"]["id"], name="Other Vendor",
                         match_key=match_key_for("Other Vendor"), currency="NGN")
        db.session.add(other)
        db.session.commit()
        other_id = other.id

    make_rule(client, headers, name="Watch this supplier",
              supplierId=supplier["id"])

    buyer = headers_for(app, org, "buyer")
    watched = create_po(client, buyer, supplier["id"])
    submit(client, buyer, watched["id"])
    assert open_request(client, headers, watched["id"]) is not None

    unwatched = create_po(client, buyer, other_id)
    submit(client, buyer, unwatched["id"])
    assert open_request(client, headers, unwatched["id"]) is None


def test_the_preview_explains_which_rule_governs_an_order(
    app, client, org, supplier
):
    """"Why did this need three signatures" is the question every approval
    system gets asked."""
    headers = headers_for(app, org, "owner")
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])

    before = client.post("/api/approvals/rules/preview",
                         json={"purchaseOrderId": po["id"]},
                         headers=headers).get_json()
    assert before["rule"] is None
    assert "default" in before["explanation"]

    make_rule(client, headers, name="Everything")
    after = client.post("/api/approvals/rules/preview",
                        json={"purchaseOrderId": po["id"]},
                        headers=headers).get_json()
    assert after["rule"]["name"] == "Everything"


# ─── Rule validation ─────────────────────────────────────────────────────────
def test_a_rule_needs_a_name_and_at_least_one_step(app, client, org):
    headers = headers_for(app, org, "owner")
    response = client.post("/api/approvals/rules",
                           json={"name": "", "steps": []}, headers=headers)
    assert response.status_code == 400
    fields = response.get_json()["fields"]
    assert "name" in fields and "steps" in fields


def test_a_rule_whose_range_can_never_match_is_refused(app, client, org):
    """Not a rule, a mistake that silently switches an approval off."""
    headers = headers_for(app, org, "owner")
    response = make_rule(client, headers, minAmount="1000", maxAmount="500")
    assert response.status_code == 400
    assert "maxAmount" in response.get_json()["fields"]


def test_a_step_naming_an_unknown_role_is_refused(app, client, org):
    headers = headers_for(app, org, "owner")
    response = make_rule(client, headers, steps=[
        {"level": 1, "approverType": "role", "approverRole": "chief_wizard"},
    ])
    assert response.status_code == 400
    assert "steps.0.approverRole" in response.get_json()["fields"]


def test_a_step_naming_someone_outside_the_organization_is_refused(
    app, client, org
):
    outsider = make_user(app, email="outsider@example.com", plan="pro")
    headers = headers_for(app, org, "owner")
    response = make_rule(client, headers, steps=[
        {"level": 1, "approverType": "user", "approverUserId": outsider["id"]},
    ])
    assert response.status_code == 400
    assert "steps.0.approverUserId" in response.get_json()["fields"]


def test_writing_rules_needs_the_admin_gate_not_the_approver_gate(
    app, client, org
):
    """Letting approvers edit the thresholds that bind them would make the
    control decorative."""
    approver = headers_for(app, org, "approver")
    assert client.get("/api/approvals/rules",
                      headers=approver).status_code == 200
    assert make_rule(client, approver).status_code == 403


def test_an_approver_can_read_the_rules(app, client, org):
    """Somebody who cannot see why a thing reached them cannot judge whether
    it should have."""
    approver = headers_for(app, org, "approver")
    body = client.get("/api/approvals/rules", headers=approver).get_json()
    assert body["canManage"] is False


# ─── Single-level chains ─────────────────────────────────────────────────────
def test_approving_the_only_level_approves_the_order(app, client, org, supplier):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)

    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    manager = headers_for(app, org, "manager")
    done = client.post(f"/api/approvals/requests/{live['id']}/approve",
                       json={"comment": "Fine."}, headers=manager)
    assert done.status_code == 200
    assert done.get_json()["approvalRequest"]["status"] == "approved"

    body = client.get(f"/api/purchase-orders/{po['id']}",
                      headers=buyer).get_json()
    assert body["purchaseOrder"]["status"] == "approved"


def test_rejecting_sends_the_order_back_to_draft_with_the_reason(
    app, client, org, supplier
):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)

    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    manager = headers_for(app, org, "manager")
    done = client.post(f"/api/approvals/requests/{live['id']}/reject",
                       json={"reason": "Use the framework supplier."},
                       headers=manager)
    assert done.status_code == 200
    assert done.get_json()["approvalRequest"]["status"] == "rejected"

    body = client.get(f"/api/purchase-orders/{po['id']}",
                      headers=buyer).get_json()["purchaseOrder"]
    assert body["status"] == "draft"
    assert body["rejectionReason"] == "Use the framework supplier."


def test_rejecting_without_a_reason_is_refused(app, client, org, supplier):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    manager = headers_for(app, org, "manager")
    response = client.post(f"/api/approvals/requests/{live['id']}/reject",
                           json={"reason": "   "}, headers=manager)
    assert response.status_code == 409
    assert response.get_json()["code"] == "REASON_REQUIRED"


# ─── Multi-level chains ──────────────────────────────────────────────────────
def test_level_two_is_not_asked_until_level_one_is_satisfied(
    app, client, org, supplier
):
    """A director should not be troubled by something their manager is going
    to reject."""
    owner = headers_for(app, org, "owner")
    make_rule(client, owner, name="Two levels", steps=[
        {"level": 1, "approverType": "role", "approverRole": FINANCE_MANAGER},
        {"level": 2, "approverType": "role", "approverRole": ADMIN},
    ])

    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    # The director cannot act yet.
    director = headers_for(app, org, "director")
    early = client.post(f"/api/approvals/requests/{live['id']}/approve",
                        headers=director)
    assert early.status_code == 409
    assert early.get_json()["code"] == "NOT_YOUR_TURN"

    manager = headers_for(app, org, "manager")
    after_one = client.post(f"/api/approvals/requests/{live['id']}/approve",
                            headers=manager).get_json()["approvalRequest"]
    assert after_one["status"] == "pending"
    assert after_one["currentLevel"] == 2

    # The order is NOT approved on one signature of a two-level chain.
    body = client.get(f"/api/purchase-orders/{po['id']}",
                      headers=buyer).get_json()
    assert body["purchaseOrder"]["status"] == "pending_approval"

    final = client.post(f"/api/approvals/requests/{live['id']}/approve",
                        headers=director).get_json()["approvalRequest"]
    assert final["status"] == "approved"
    body = client.get(f"/api/purchase-orders/{po['id']}",
                      headers=buyer).get_json()
    assert body["purchaseOrder"]["status"] == "approved"


def test_a_rejection_at_level_one_ends_the_whole_request(
    app, client, org, supplier
):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner, name="Two levels", steps=[
        {"level": 1, "approverType": "role", "approverRole": FINANCE_MANAGER},
        {"level": 2, "approverType": "role", "approverRole": ADMIN},
    ])
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    manager = headers_for(app, org, "manager")
    client.post(f"/api/approvals/requests/{live['id']}/reject",
                json={"reason": "No."}, headers=manager)

    detail = request_detail(client, buyer, live["id"])
    assert detail["status"] == "rejected"
    # The second level was never asked.
    level_two = [s for s in detail["steps"] if s["level"] == 2]
    assert all(s["status"] in ("pending", "skipped") for s in level_two)
    assert all(s["status"] != "approved" for s in level_two)


def test_any_one_approver_at_a_level_is_enough_by_default(
    app, client, org, supplier
):
    owner = headers_for(app, org, "owner")
    # Two roles at the same level: parallel, either will do.
    make_rule(client, owner, name="Either", steps=[
        {"level": 1, "approverType": "role", "approverRole": FINANCE_MANAGER},
        {"level": 1, "approverType": "role", "approverRole": APPROVER},
    ])
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])
    assert len(live["steps"]) == 2

    approver = headers_for(app, org, "approver")
    done = client.post(f"/api/approvals/requests/{live['id']}/approve",
                       headers=approver).get_json()["approvalRequest"]
    assert done["status"] == "approved"
    # The other approver is marked skipped, not left in their queue forever.
    assert any(s["status"] == "skipped" for s in done["steps"])


def test_require_all_makes_every_approver_at_the_level_sign(
    app, client, org, supplier
):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner, name="Both", steps=[
        {"level": 1, "approverType": "role", "approverRole": FINANCE_MANAGER,
         "requireAll": True},
        {"level": 1, "approverType": "role", "approverRole": APPROVER,
         "requireAll": True},
    ])
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    manager = headers_for(app, org, "manager")
    first = client.post(f"/api/approvals/requests/{live['id']}/approve",
                        headers=manager).get_json()["approvalRequest"]
    assert first["status"] == "pending"

    approver = headers_for(app, org, "approver")
    second = client.post(f"/api/approvals/requests/{live['id']}/approve",
                         headers=approver).get_json()["approvalRequest"]
    assert second["status"] == "approved"


def test_a_role_resolves_to_every_member_holding_it(app, client, org, supplier):
    owner = headers_for(app, org, "owner")
    extra = make_user(app, email="manager2@example.com", plan="pro")
    join_org(app, org["org"], extra, FINANCE_MANAGER)

    make_rule(client, owner)
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])

    live = open_request(client, buyer, po["id"])
    assert len(live["steps"]) == 2


# ─── Self-approval ───────────────────────────────────────────────────────────
def test_you_cannot_approve_a_request_you_submitted(app, client, org, supplier):
    owner = headers_for(app, org, "owner")
    # The manager both raises and would approve.
    make_rule(client, owner)

    manager = headers_for(app, org, "manager")
    po = create_po(client, manager, supplier["id"])
    submit(client, manager, po["id"])
    live = open_request(client, manager, po["id"])

    response = client.post(f"/api/approvals/requests/{live['id']}/approve",
                           headers=manager)
    assert response.status_code == 409
    assert response.get_json()["code"] == "SELF_APPROVAL"


def test_a_sole_approver_may_approve_their_own(app, client, supplier):
    """Refusing in a one-person organization would make approval impossible
    rather than safer."""
    solo = make_user(app, email="solo@example.com", plan="pro")
    headers = auth_header(app, solo)

    from extensions import db
    from models import Supplier
    from suppliers import match_key_for

    with app.app_context():
        row = Supplier(organization_id=solo["organization_id"], name="V",
                       match_key=match_key_for("V"), currency="NGN")
        db.session.add(row)
        db.session.commit()
        supplier_id = row.id

    from roles import OWNER

    make_rule(client, headers, steps=[
        {"level": 1, "approverType": "role", "approverRole": OWNER},
    ])
    po = create_po(client, headers, supplier_id)
    submit(client, headers, po["id"])
    live = open_request(client, headers, po["id"])

    done = client.post(f"/api/approvals/requests/{live['id']}/approve",
                       headers=headers)
    assert done.status_code == 200
    assert done.get_json()["approvalRequest"]["status"] == "approved"


# ─── The chain cannot be bypassed ────────────────────────────────────────────
def test_the_order_endpoint_refuses_to_approve_around_a_live_chain(
    app, client, org, supplier
):
    """Approving the order directly while people are partway through signing
    it would make the chain a decoration and the audit trail a fiction."""
    owner = headers_for(app, org, "owner")
    make_rule(client, owner, name="Two levels", steps=[
        {"level": 1, "approverType": "role", "approverRole": FINANCE_MANAGER},
        {"level": 2, "approverType": "role", "approverRole": ADMIN},
    ])
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])

    direct = client.post(f"/api/purchase-orders/{po['id']}/approve",
                         headers=headers_for(app, org, "director"))
    assert direct.status_code == 409
    assert direct.get_json()["code"] == "IN_WORKFLOW"

    body = client.get(f"/api/purchase-orders/{po['id']}",
                      headers=buyer).get_json()
    assert body["purchaseOrder"]["status"] == "pending_approval"


def test_the_order_endpoint_refuses_to_reject_around_a_live_chain(
    app, client, org, supplier
):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])

    direct = client.post(f"/api/purchase-orders/{po['id']}/reject",
                         json={"reason": "no"},
                         headers=headers_for(app, org, "manager"))
    assert direct.status_code == 409
    assert direct.get_json()["code"] == "IN_WORKFLOW"


def test_with_no_rule_the_order_keeps_its_old_single_approval(
    app, client, org, supplier
):
    """What makes workflows additive: an organization that has configured
    nothing behaves exactly as it did before P2.5."""
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    assert open_request(client, buyer, po["id"]) is None

    done = client.post(f"/api/purchase-orders/{po['id']}/approve",
                       headers=headers_for(app, org, "manager"))
    assert done.status_code == 200
    assert done.get_json()["purchaseOrder"]["status"] == "approved"


def test_somebody_not_in_the_chain_cannot_act(app, client, org, supplier):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    # The approver role holds approvals:act but is not in THIS chain.
    response = client.post(f"/api/approvals/requests/{live['id']}/approve",
                           headers=headers_for(app, org, "approver"))
    assert response.status_code == 409
    assert response.get_json()["code"] == "NOT_YOUR_TURN"


def test_an_accountant_cannot_act_on_an_approval(app, client, org, supplier):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    response = client.post(f"/api/approvals/requests/{live['id']}/approve",
                           headers=headers_for(app, org, "clerk"))
    assert response.status_code == 403


# ─── Information requests ────────────────────────────────────────────────────
def test_an_approver_can_ask_a_question_without_deciding(
    app, client, org, supplier
):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    manager = headers_for(app, org, "manager")
    asked = client.post(f"/api/approvals/requests/{live['id']}/ask",
                        json={"question": "Is this the framework price?"},
                        headers=manager)
    assert asked.status_code == 200
    assert asked.get_json()["approvalRequest"]["status"] == "info_requested"

    answered = client.post(f"/api/approvals/requests/{live['id']}/answer",
                           json={"answer": "Yes, schedule 4."}, headers=buyer)
    assert answered.status_code == 200
    detail = answered.get_json()["approvalRequest"]
    assert detail["status"] == "pending"
    actions = [event["action"] for event in detail["history"]]
    assert "info_requested" in actions and "info_provided" in actions


def test_the_step_stays_with_the_approver_while_they_wait(
    app, client, org, supplier
):
    """Asking a question is not handing the request back."""
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    manager = headers_for(app, org, "manager")
    client.post(f"/api/approvals/requests/{live['id']}/ask",
                json={"question": "Why?"}, headers=manager)
    client.post(f"/api/approvals/requests/{live['id']}/answer",
                json={"answer": "Because."}, headers=buyer)

    done = client.post(f"/api/approvals/requests/{live['id']}/approve",
                       headers=manager)
    assert done.status_code == 200


def test_answering_when_nothing_was_asked_is_refused(app, client, org, supplier):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    response = client.post(f"/api/approvals/requests/{live['id']}/answer",
                           json={"answer": "hello"}, headers=buyer)
    assert response.status_code == 409
    assert response.get_json()["code"] == "NOTHING_ASKED"


# ─── Delegation ──────────────────────────────────────────────────────────────
def test_a_delegate_can_approve_on_somebody_elses_behalf(
    app, client, org, supplier
):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    manager = headers_for(app, org, "manager")

    created = client.post("/api/approvals/delegations", json={
        "toUserId": org["people"]["approver"]["id"],
        "reason": "Annual leave",
    }, headers=manager)
    assert created.status_code == 201

    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    approver = headers_for(app, org, "approver")
    done = client.post(f"/api/approvals/requests/{live['id']}/approve",
                       headers=approver)
    assert done.status_code == 200
    detail = done.get_json()["approvalRequest"]
    assert detail["status"] == "approved"
    # Both parties on the record: "approved by X on behalf of Y". Asserted on
    # ids, not display names - conftest gives every test user the same name,
    # so comparing labels would pass or fail for the wrong reason.
    signed = [s for s in detail["steps"] if s["status"] == "approved"][0]
    assert signed["onBehalf"] is True
    assert signed["approverUserId"] == org["people"]["manager"]["id"]
    assert signed["actedBy"] is not None


def test_a_delegation_that_has_not_started_does_not_apply(
    app, client, org, supplier
):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    manager = headers_for(app, org, "manager")
    client.post("/api/approvals/delegations", json={
        "toUserId": org["people"]["approver"]["id"],
        "startsOn": "2099-01-01",
    }, headers=manager)

    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    response = client.post(f"/api/approvals/requests/{live['id']}/approve",
                           headers=headers_for(app, org, "approver"))
    assert response.status_code == 409


def test_an_expired_delegation_does_not_apply(app, client, org, supplier):
    """The holiday it was created for ended two years ago."""
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    manager = headers_for(app, org, "manager")
    client.post("/api/approvals/delegations", json={
        "toUserId": org["people"]["approver"]["id"],
        "startsOn": "2020-01-01", "endsOn": "2020-01-14",
    }, headers=manager)

    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    response = client.post(f"/api/approvals/requests/{live['id']}/approve",
                           headers=headers_for(app, org, "approver"))
    assert response.status_code == 409


def test_you_cannot_delegate_somebody_elses_authority_to_yourself(
    app, client, org
):
    """The whole point of the check."""
    approver = headers_for(app, org, "approver")
    response = client.post("/api/approvals/delegations", json={
        "fromUserId": org["people"]["manager"]["id"],
        "toUserId": org["people"]["approver"]["id"],
    }, headers=approver)
    assert response.status_code == 403


def test_an_administrator_can_delegate_for_somebody_who_has_already_left(
    app, client, org
):
    owner = headers_for(app, org, "owner")
    response = client.post("/api/approvals/delegations", json={
        "fromUserId": org["people"]["manager"]["id"],
        "toUserId": org["people"]["approver"]["id"],
        "reason": "Phone off, flight boarded.",
    }, headers=owner)
    assert response.status_code == 201


def test_delegating_to_yourself_is_refused(app, client, org):
    manager = headers_for(app, org, "manager")
    response = client.post("/api/approvals/delegations", json={
        "toUserId": org["people"]["manager"]["id"],
    }, headers=manager)
    assert response.status_code == 400


def test_a_delegation_can_be_ended_and_is_kept_as_a_record(app, client, org):
    manager = headers_for(app, org, "manager")
    created = client.post("/api/approvals/delegations", json={
        "toUserId": org["people"]["approver"]["id"],
    }, headers=manager).get_json()["delegation"]

    ended = client.delete(f"/api/approvals/delegations/{created['id']}",
                          headers=manager)
    assert ended.status_code == 200
    assert ended.get_json()["delegation"]["active"] is False

    listed = client.get("/api/approvals/delegations",
                        headers=manager).get_json()["delegations"]
    assert any(d["id"] == created["id"] for d in listed)


# ─── The queue, reminders and history ────────────────────────────────────────
def test_mine_shows_what_is_waiting_on_this_person(app, client, org, supplier):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])

    manager = headers_for(app, org, "manager")
    mine = client.get("/api/approvals/requests?mine=1",
                      headers=manager).get_json()
    assert mine["total"] == 1

    # The approver is not in this chain.
    theirs = client.get("/api/approvals/requests?mine=1",
                        headers=headers_for(app, org, "approver")).get_json()
    assert theirs["total"] == 0


def test_mine_includes_what_a_delegate_may_act_on(app, client, org, supplier):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    manager = headers_for(app, org, "manager")
    client.post("/api/approvals/delegations", json={
        "toUserId": org["people"]["approver"]["id"],
    }, headers=manager)

    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])

    mine = client.get("/api/approvals/requests?mine=1",
                      headers=headers_for(app, org, "approver")).get_json()
    assert mine["total"] == 1


def test_a_reminder_is_recorded_whether_or_not_an_email_leaves(
    app, client, org, supplier
):
    """"I chased them twice" should be a fact, not a claim."""
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    reminded = client.post(f"/api/approvals/requests/{live['id']}/remind",
                           headers=buyer)
    assert reminded.status_code == 200
    detail = reminded.get_json()["approvalRequest"]
    assert detail["lastRemindedAt"] is not None
    assert "reminded" in [e["action"] for e in detail["history"]]


def test_the_history_records_every_step_in_order(app, client, org, supplier):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner, name="Two levels", steps=[
        {"level": 1, "approverType": "role", "approverRole": FINANCE_MANAGER},
        {"level": 2, "approverType": "role", "approverRole": ADMIN},
    ])
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    client.post(f"/api/approvals/requests/{live['id']}/approve",
                json={"comment": "ok"}, headers=headers_for(app, org, "manager"))
    client.post(f"/api/approvals/requests/{live['id']}/approve",
                headers=headers_for(app, org, "director"))

    detail = request_detail(client, buyer, live["id"])
    actions = [e["action"] for e in detail["history"]]
    assert actions[0] == "submitted"
    assert actions.count("approved") == 2
    assert actions.count("level_completed") == 2


def test_a_completed_request_cannot_be_acted_on_again(app, client, org, supplier):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    manager = headers_for(app, org, "manager")
    client.post(f"/api/approvals/requests/{live['id']}/approve", headers=manager)
    again = client.post(f"/api/approvals/requests/{live['id']}/approve",
                        headers=manager)
    assert again.status_code == 409
    assert again.get_json()["code"] == "NOT_OPEN"


def test_editing_a_rule_does_not_rewrite_a_chain_already_in_flight(
    app, client, org, supplier
):
    """The people who signed it signed a specific chain. An audit trail that
    changes shape retrospectively is not one."""
    owner = headers_for(app, org, "owner")
    rule = make_rule(client, owner).get_json()["rule"]

    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])
    assert {s["approverRole"] for s in live["steps"]} == {FINANCE_MANAGER}

    client.patch(f"/api/approvals/rules/{rule['id']}", json={
        "name": "Changed", "subjectType": "purchase_order",
        "steps": [{"level": 1, "approverType": "role", "approverRole": ADMIN}],
    }, headers=owner)

    after = request_detail(client, buyer, live["id"])
    assert {s["approverRole"] for s in after["steps"]} == {FINANCE_MANAGER}
    # And the manager can still sign it.
    done = client.post(f"/api/approvals/requests/{live['id']}/approve",
                       headers=headers_for(app, org, "manager"))
    assert done.status_code == 200


def test_a_chain_nobody_can_satisfy_announces_itself(app, client, org, supplier):
    """A request silently parked forever is worse than one that says it is
    stuck."""
    from extensions import db
    from models import ApprovalRequestStep

    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    # Everyone at the current level leaves.
    with app.app_context():
        for step in ApprovalRequestStep.query.filter_by(
            request_id=live["id"]
        ).all():
            step.status = ApprovalRequestStep.SKIPPED
        db.session.commit()

    detail = request_detail(client, buyer, live["id"])
    assert detail["stuck"] is True


def test_a_request_can_be_cancelled(app, client, org, supplier):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    cancelled = client.post(f"/api/approvals/requests/{live['id']}/cancel",
                            json={"reason": "Raised in error."},
                            headers=headers_for(app, org, "manager"))
    assert cancelled.status_code == 200
    assert cancelled.get_json()["approvalRequest"]["status"] == "cancelled"


# ─── Tenancy and the paywall ─────────────────────────────────────────────────
def test_approvals_never_cross_an_organization_boundary(app, client, org, supplier):
    owner = headers_for(app, org, "owner")
    make_rule(client, owner)
    buyer = headers_for(app, org, "buyer")
    po = create_po(client, buyer, supplier["id"])
    submit(client, buyer, po["id"])
    live = open_request(client, buyer, po["id"])

    stranger = make_user(app, email="stranger@example.com", plan="pro")
    stranger_headers = auth_header(app, stranger)
    assert client.get(f"/api/approvals/requests/{live['id']}",
                      headers=stranger_headers).status_code == 404
    assert client.get("/api/approvals/rules",
                      headers=stranger_headers).get_json()["rules"] == []


def test_a_viewer_cannot_act_on_approvals(app, client, org):
    watcher = make_user(app, email="watcher@example.com", plan="pro")
    join_org(app, org["org"], watcher, VIEWER)
    headers = {**auth_header(app, watcher), **org_header(app, watcher, org["org"])}
    # A viewer holds approvals:read, so the queue is visible...
    assert client.get("/api/approvals/requests", headers=headers).status_code == 200
    # ...but not approvals:act.
    assert client.post("/api/approvals/requests/x/approve",
                       headers=headers).status_code == 403


def test_approvals_are_behind_the_payables_paywall(app, client):
    free = make_user(app, email="free@example.com", plan="free")
    response = client.get("/api/approvals/rules", headers=auth_header(app, free))
    assert response.status_code == 402
    assert response.get_json()["capability"] == "payables"
