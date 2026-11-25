"""Approval workflows: the rules, and the requests they produce.

Two permissions, and the split matters. Writing the RULES is
`organization:settings` — deciding who must approve what is an administrative
act, and letting approvers edit the thresholds that bind them would make the
control decorative. Acting on a REQUEST is `approvals:act`.

Delegation is managed by its owner: you may hand your own authority to
somebody else, and an administrator may do it for you (for the person who has
already left for the airport). Nobody else can grant themselves your signature.
"""
import logging
from datetime import datetime

from flask import Blueprint, g, jsonify, request

from approvals import (
    ApprovalError,
    active_delegations,
    approve,
    cancel,
    chain_is_broken,
    find_rule,
    may_act_for,
    open_request_for,
    provide_information,
    record_reminder,
    reject,
    request_information,
    start_request,
    step_for_actor,
    waiting_on,
)
from auth import api_or_login_required
from extensions import db
from models import (
    ApprovalDelegation,
    ApprovalRequest,
    ApprovalRequestStep,
    ApprovalRule,
    ApprovalRuleStep,
    Extraction,
    OrganizationMembership,
    PurchaseOrder,
    Supplier,
    User,
)
from money import as_json, money
from plans import PAYABLES, PAYABLES_FEATURE
from roles import APPROVALS_ACT, APPROVALS_READ, ORG_SETTINGS, is_valid_role
from tenancy import (
    current_organization,
    has_permission,
    require_capability,
    require_permission,
    scoped,
)

approval_bp = Blueprint("approvals", __name__, url_prefix="/api/approvals")
logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100
MAX_NAME = 200
MAX_COMMENT = 1000
MAX_RULE_STEPS = 20


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _labels_for(user_ids) -> dict:
    """Display names for a set of users, in one query."""
    ids = {uid for uid in user_ids if uid}
    if not ids:
        return {}
    return {
        user.id: (user.name or user.email)
        for user in User.query.filter(User.id.in_(ids)).all()
    }


def _request_labels(req: ApprovalRequest) -> dict:
    ids = {req.submitted_by_user_id}
    for step in req.steps:
        ids.add(step.approver_user_id)
        ids.add(step.acted_by_user_id)
    for event in req.events:
        ids.add(event.user_id)
        ids.add(event.target_user_id)
    return _labels_for(ids)


def _subject_of(req: ApprovalRequest) -> dict | None:
    """A thumbnail of what is being approved, so the queue is readable."""
    if req.subject_type == ApprovalRule.PURCHASE_ORDER:
        po = PurchaseOrder.query.filter_by(
            id=req.subject_id, organization_id=req.organization_id
        ).first()
        if po is None:
            return None
        supplier = Supplier.query.filter_by(id=po.supplier_id).first()
        return {
            "kind": "purchase_order",
            "id": po.id,
            "reference": po.po_number,
            "status": po.status,
            "total": as_json(po.total),
            "currency": po.currency,
            "supplierName": supplier.name if supplier else None,
            "department": po.department,
        }
    row = Extraction.query.filter_by(
        id=req.subject_id, organization_id=req.organization_id
    ).first()
    if row is None:
        return None
    return {
        "kind": "invoice",
        "id": row.id,
        "reference": row.invoice_number or row.file_name,
        "status": row.status,
        "total": as_json(row.total),
        "currency": row.currency,
        "supplierName": row.vendor_name,
    }


def _detail(req: ApprovalRequest) -> dict:
    labels = _request_labels(req)
    payload = req.public(labels=labels, subject=_subject_of(req))
    payload["waitingOn"] = [labels.get(uid) for uid in waiting_on(req)]
    # Surfaced rather than left for a reader to deduce from an empty step
    # list: a request nobody can act on must announce itself.
    payload["stuck"] = chain_is_broken(req)
    payload["canAct"] = step_for_actor(req, g.user.id) is not None
    return {"approvalRequest": payload}


def _facts_for_po(po: PurchaseOrder) -> dict:
    return {
        "amount": po.total,
        "currency": po.currency,
        "department": po.department,
        "costCenter": po.cost_center,
        "project": po.project,
        "category": po.category,
        "supplierId": po.supplier_id,
    }


# ─── Rules ───────────────────────────────────────────────────────────────────
def _validate_rule(body, organization_id) -> tuple[dict, list, dict]:
    errors = {}
    fields = {}

    name = (body.get("name") or "").strip()
    if not name:
        errors["name"] = "Give this rule a name."
    elif len(name) > MAX_NAME:
        errors["name"] = "That name is too long."
    fields["name"] = name[:MAX_NAME]

    subject = (body.get("subjectType") or ApprovalRule.PURCHASE_ORDER).strip()
    if subject not in ApprovalRule.SUBJECTS:
        errors["subjectType"] = "Choose purchase_order or invoice."
    fields["subject_type"] = subject

    for key, column in (("minAmount", "min_amount"), ("maxAmount", "max_amount")):
        raw = body.get(key)
        if raw in (None, ""):
            fields[column] = None
            continue
        parsed = money(raw)
        if parsed is None:
            errors[key] = "Enter an amount."
        elif parsed < 0:
            errors[key] = "An amount cannot be negative."
        else:
            fields[column] = parsed

    low, high = fields.get("min_amount"), fields.get("max_amount")
    if low is not None and high is not None and low > high:
        # A rule that can never match is not a rule, it is a mistake that
        # silently switches an approval off.
        errors["maxAmount"] = "The maximum must be at or above the minimum."

    for key, column, limit in (
        ("currency", "currency", 3),
        ("department", "department", 120),
        ("costCenter", "cost_center", 120),
        ("project", "project", 120),
        ("category", "category", 120),
    ):
        value = (body.get(key) or "").strip() or None
        if value and len(value) > limit:
            errors[key] = f"Keep this under {limit} characters."
        fields[column] = value.upper() if (value and column == "currency") else value

    supplier_id = (body.get("supplierId") or "").strip() or None
    if supplier_id:
        supplier = Supplier.query.filter_by(
            id=supplier_id, organization_id=organization_id
        ).first()
        if supplier is None:
            errors["supplierId"] = "That supplier does not exist."
    fields["supplier_id"] = supplier_id

    fields["active"] = bool(body.get("active", True))
    try:
        fields["priority"] = int(body.get("priority") or 0)
    except (TypeError, ValueError):
        errors["priority"] = "Enter a whole number."

    steps_raw = body.get("steps")
    steps = []
    if not isinstance(steps_raw, list) or not steps_raw:
        errors["steps"] = "Add at least one approval step."
    elif len(steps_raw) > MAX_RULE_STEPS:
        errors["steps"] = f"A rule cannot have more than {MAX_RULE_STEPS} steps."
    else:
        for index, raw in enumerate(steps_raw):
            if not isinstance(raw, dict):
                errors[f"steps.{index}"] = "Expected an object."
                continue
            try:
                level = int(raw.get("level") or 1)
            except (TypeError, ValueError):
                errors[f"steps.{index}.level"] = "Enter a whole number."
                continue
            if level < 1:
                errors[f"steps.{index}.level"] = "Levels start at 1."
                continue

            kind = (raw.get("approverType") or ApprovalRuleStep.BY_ROLE).strip()
            role = (raw.get("approverRole") or "").strip() or None
            user_id = (raw.get("approverUserId") or "").strip() or None

            if kind == ApprovalRuleStep.BY_USER:
                if not user_id:
                    errors[f"steps.{index}.approverUserId"] = "Choose a person."
                    continue
                member = OrganizationMembership.query.filter_by(
                    organization_id=organization_id, user_id=user_id
                ).first()
                if member is None:
                    errors[f"steps.{index}.approverUserId"] = (
                        "That person is not in this organization."
                    )
                    continue
                role = None
            else:
                kind = ApprovalRuleStep.BY_ROLE
                if not role or not is_valid_role(role):
                    errors[f"steps.{index}.approverRole"] = "Choose a valid role."
                    continue
                user_id = None

            steps.append({
                "level": level,
                "approver_type": kind,
                "approver_role": role,
                "approver_user_id": user_id,
                "require_all": bool(raw.get("requireAll", False)),
            })

    return fields, steps, errors


@approval_bp.get("/rules")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_READ)
def list_rules():
    """Everyone who can see approvals can read the rules.

    Deliberate: an approver who cannot see why something reached them cannot
    sensibly judge whether it should have.
    """
    rules = (
        scoped(ApprovalRule)
        .order_by(ApprovalRule.priority.desc(), ApprovalRule.created_at.asc())
        .limit(MAX_PAGE_SIZE)
        .all()
    )
    supplier_ids = {rule.supplier_id for rule in rules if rule.supplier_id}
    names = {
        s.id: s.name
        for s in Supplier.query.filter(Supplier.id.in_(supplier_ids)).all()
    } if supplier_ids else {}
    return jsonify({
        "rules": [
            rule.public(supplier_name=names.get(rule.supplier_id))
            for rule in rules
        ],
        "canManage": has_permission(ORG_SETTINGS),
    })


@approval_bp.post("/rules")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(ORG_SETTINGS)
def create_rule():
    organization = current_organization()
    body = request.get_json(silent=True) or {}
    fields, steps, errors = _validate_rule(body, organization.id)
    if errors:
        return jsonify({"error": "Some details need fixing.",
                        "fields": errors}), 400

    rule = ApprovalRule(
        organization_id=organization.id,
        created_by_user_id=g.user.id,
        **fields,
    )
    db.session.add(rule)
    db.session.flush()
    for step in steps:
        db.session.add(ApprovalRuleStep(
            rule_id=rule.id, organization_id=organization.id, **step
        ))
    db.session.commit()
    return jsonify({"rule": rule.public()}), 201


@approval_bp.patch("/rules/<rule_id>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(ORG_SETTINGS)
def update_rule(rule_id):
    """Replace a rule's conditions and steps.

    Requests already in flight keep the chain they were built with: this
    rewrites the rule, never an approval somebody is partway through.
    """
    rule = scoped(ApprovalRule).filter(ApprovalRule.id == rule_id).first()
    if rule is None:
        return jsonify({"error": "Rule not found."}), 404

    body = request.get_json(silent=True) or {}
    fields, steps, errors = _validate_rule(body, rule.organization_id)
    if errors:
        return jsonify({"error": "Some details need fixing.",
                        "fields": errors}), 400

    for key, value in fields.items():
        setattr(rule, key, value)
    rule.steps.clear()
    db.session.flush()
    for step in steps:
        db.session.add(ApprovalRuleStep(
            rule_id=rule.id, organization_id=rule.organization_id, **step
        ))
    db.session.commit()
    return jsonify({"rule": rule.public()})


@approval_bp.delete("/rules/<rule_id>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(ORG_SETTINGS)
def delete_rule(rule_id):
    """Deactivate a rule. Requests it already produced are untouched."""
    rule = scoped(ApprovalRule).filter(ApprovalRule.id == rule_id).first()
    if rule is None:
        return jsonify({"error": "Rule not found."}), 404
    rule.active = False
    db.session.commit()
    return jsonify({"rule": rule.public()})


@approval_bp.post("/rules/preview")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_READ)
def preview_rule():
    """Which rule would govern a given purchase order, and who it would ask.

    Worth having as its own endpoint: "why did this need three signatures"
    is the question every approval system gets asked, and answering it by
    reading the rule table by eye is how people lose faith in it.
    """
    body = request.get_json(silent=True) or {}
    po_id = (body.get("purchaseOrderId") or "").strip()
    if not po_id:
        return jsonify({"error": "Name a purchase order.",
                        "fields": {"purchaseOrderId": "Required."}}), 400
    po = scoped(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404

    rule = find_rule(po.organization_id, ApprovalRule.PURCHASE_ORDER,
                     _facts_for_po(po))
    if rule is None:
        return jsonify({
            "rule": None,
            "explanation": (
                "No approval rule matches this order, so it follows the "
                "default: one approval from anyone who can approve."
            ),
        })
    return jsonify({
        "rule": rule.public(),
        "explanation": f"'{rule.name}' matches this order.",
    })


# ─── The queue ───────────────────────────────────────────────────────────────
@approval_bp.get("/requests")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_READ)
def list_requests():
    """Approval requests. `mine=1` narrows to what is waiting on this person.

    "Mine" includes requests waiting on somebody who has delegated to them,
    because a delegate who cannot see the queue cannot act on it.
    """
    organization = current_organization()
    page = max(1, request.args.get("page", type=int) or 1)
    size = min(MAX_PAGE_SIZE, max(1, request.args.get("perPage", type=int) or 25))

    query = scoped(ApprovalRequest)

    status = (request.args.get("status") or "").strip().lower()
    if status == "open":
        query = query.filter(
            ApprovalRequest.status.in_(ApprovalRequest.OPEN_STATUSES)
        )
    elif status in ApprovalRequest.STATUSES:
        query = query.filter(ApprovalRequest.status == status)

    subject = (request.args.get("subjectType") or "").strip()
    if subject in ApprovalRule.SUBJECTS:
        query = query.filter(ApprovalRequest.subject_type == subject)

    if request.args.get("mine") in ("1", "true", "yes"):
        acting_for = {g.user.id} | {
            d.from_user_id
            for d in active_delegations(organization.id, g.user.id)
        }
        query = query.filter(
            ApprovalRequest.id.in_(
                db.session.query(ApprovalRequestStep.request_id).filter(
                    ApprovalRequestStep.approver_user_id.in_(acting_for),
                    ApprovalRequestStep.status == ApprovalRequestStep.PENDING,
                )
            ),
            ApprovalRequest.status.in_(ApprovalRequest.OPEN_STATUSES),
        )

    total = query.order_by(None).count()
    rows = (
        query.order_by(ApprovalRequest.submitted_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    labels = _labels_for({row.submitted_by_user_id for row in rows})
    items = []
    for row in rows:
        items.append({
            "id": row.id,
            "subjectType": row.subject_type,
            "subjectId": row.subject_id,
            "status": row.status,
            "currentLevel": row.current_level,
            "ruleName": row.rule_name,
            "amount": as_json(row.amount),
            "currency": row.currency,
            "submittedBy": labels.get(row.submitted_by_user_id),
            "submittedAt": row.submitted_at.isoformat() + "Z"
            if row.submitted_at else None,
            "subject": _subject_of(row),
            "waitingOn": len(waiting_on(row)),
            "stuck": chain_is_broken(row),
        })

    return jsonify({
        "requests": items,
        "page": page,
        "perPage": size,
        "total": total,
        "pages": max(1, (total + size - 1) // size),
    })


@approval_bp.get("/requests/<request_id>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_READ)
def get_request(request_id):
    req = scoped(ApprovalRequest).filter(ApprovalRequest.id == request_id).first()
    if req is None:
        return jsonify({"error": "Approval request not found."}), 404
    return jsonify(_detail(req))


def _act(request_id, handler, permission=APPROVALS_ACT):
    req = scoped(ApprovalRequest).filter(ApprovalRequest.id == request_id).first()
    if req is None:
        return jsonify({"error": "Approval request not found."}), 404
    body = request.get_json(silent=True) or {}
    try:
        handler(req, body)
    except ApprovalError as exc:
        db.session.rollback()
        return jsonify({"error": exc.message, "code": exc.code}), 409
    db.session.commit()
    _apply_outcome(req)
    return jsonify(_detail(req))


def _apply_outcome(req: ApprovalRequest) -> None:
    """Push a completed decision onto the document it was about.

    Kept here rather than inside the engine: the engine knows about approval,
    not about what a purchase order's lifecycle permits, and a module that
    knows both is one that can only be tested through both.
    """
    if req.subject_type != ApprovalRule.PURCHASE_ORDER:
        return
    if req.status not in (ApprovalRequest.APPROVED, ApprovalRequest.REJECTED):
        return

    po = PurchaseOrder.query.filter_by(
        id=req.subject_id, organization_id=req.organization_id
    ).first()
    if po is None or po.status != PurchaseOrder.PENDING_APPROVAL:
        return

    from purchase_orders import TransitionError, transition

    target = (
        PurchaseOrder.APPROVED if req.status == ApprovalRequest.APPROVED
        else PurchaseOrder.DRAFT
    )
    try:
        transition(po, target, user_id=g.user.id,
                   reason=req.outcome_comment, skip_self_check=True)
    except TransitionError:
        logger.exception("could not apply approval outcome to PO %s", po.id)
        db.session.rollback()
        return
    db.session.commit()


@approval_bp.post("/requests/<request_id>/approve")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_ACT)
def approve_request(request_id):
    return _act(request_id, lambda req, body: approve(
        req, g.user.id, comment=(body.get("comment") or "")[:MAX_COMMENT] or None,
    ))


@approval_bp.post("/requests/<request_id>/reject")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_ACT)
def reject_request(request_id):
    return _act(request_id, lambda req, body: reject(
        req, g.user.id, reason=(body.get("reason") or ""),
    ))


@approval_bp.post("/requests/<request_id>/ask")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_ACT)
def ask_request(request_id):
    return _act(request_id, lambda req, body: request_information(
        req, g.user.id, question=(body.get("question") or ""),
    ))


@approval_bp.post("/requests/<request_id>/answer")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_READ)
def answer_request(request_id):
    """Answering is not an approval act — it is the submitter replying."""
    return _act(request_id, lambda req, body: provide_information(
        req, g.user.id, answer=(body.get("answer") or ""),
    ))


@approval_bp.post("/requests/<request_id>/cancel")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_ACT)
def cancel_request(request_id):
    return _act(request_id, lambda req, body: cancel(
        req, g.user.id, reason=(body.get("reason") or "")[:MAX_COMMENT] or None,
    ))


@approval_bp.post("/requests/<request_id>/remind")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_READ)
def remind_request(request_id):
    """Nudge whoever the request is waiting on.

    Recorded in the history whether or not an email leaves the building, so
    "I chased them twice" is a fact rather than a claim.
    """
    req = scoped(ApprovalRequest).filter(ApprovalRequest.id == request_id).first()
    if req is None:
        return jsonify({"error": "Approval request not found."}), 404
    if not req.is_open:
        return jsonify({"error": f"This request is already {req.status}.",
                        "code": "NOT_OPEN"}), 409

    targets = waiting_on(req)
    if not targets:
        return jsonify({"error": "Nobody is currently assigned to this request.",
                        "code": "NOBODY_WAITING"}), 409

    record_reminder(req, g.user.id, targets)
    db.session.commit()

    _notify_approvers(req, targets)
    return jsonify(_detail(req))


def _notify_approvers(req: ApprovalRequest, user_ids: list[str]) -> None:
    """Email the people a request is waiting on. Never fatal.

    A notification that fails must not undo a decision that succeeded, so
    this runs after the commit and swallows its own errors.
    """
    try:
        from config import Config
        from emails import send_custom

        subject = _subject_of(req) or {}
        reference = subject.get("reference") or req.subject_id
        link = f"{Config.APP_URL.rstrip('/')}/dashboard/approvals/{req.id}"
        users = User.query.filter(User.id.in_(user_ids)).all()
        for user in users:
            send_custom(
                user.email,
                f"Approval needed: {reference}",
                "An approval is waiting for you",
                f'<p style="color:#94a3b8">{reference} is waiting for your '
                f'approval.</p><p><a href="{link}">Review it</a></p>',
            )
    except Exception:
        logger.exception("approval notification failed for request %s", req.id)


# ─── Delegation ──────────────────────────────────────────────────────────────
@approval_bp.get("/delegations")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_READ)
def list_delegations():
    rows = (
        scoped(ApprovalDelegation)
        .order_by(ApprovalDelegation.created_at.desc())
        .limit(MAX_PAGE_SIZE)
        .all()
    )
    labels = _labels_for(
        {row.from_user_id for row in rows} | {row.to_user_id for row in rows}
    )
    return jsonify({
        "delegations": [row.public(labels=labels) for row in rows],
        "canManageOthers": has_permission(ORG_SETTINGS),
    })


@approval_bp.post("/delegations")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_READ)
def create_delegation():
    """Hand your approval authority to somebody else for a period.

    You may delegate your own; an administrator may delegate anyone's, for the
    person who has already left for the airport. Nobody can grant themselves
    somebody else's signature — which is the whole point of the check.
    """
    organization = current_organization()
    body = request.get_json(silent=True) or {}
    errors = {}

    from_user_id = (body.get("fromUserId") or g.user.id).strip()
    to_user_id = (body.get("toUserId") or "").strip()

    if from_user_id != g.user.id and not has_permission(ORG_SETTINGS):
        return jsonify({
            "error": "You can only delegate your own approvals.",
            "code": "FORBIDDEN",
        }), 403

    if not to_user_id:
        errors["toUserId"] = "Choose who should approve in your place."
    elif to_user_id == from_user_id:
        errors["toUserId"] = "Delegating to yourself changes nothing."
    else:
        member = OrganizationMembership.query.filter_by(
            organization_id=organization.id, user_id=to_user_id
        ).first()
        if member is None:
            errors["toUserId"] = "That person is not in this organization."

    starts_on = (body.get("startsOn") or "").strip() or None
    ends_on = (body.get("endsOn") or "").strip() or None
    if starts_on and ends_on and starts_on > ends_on:
        errors["endsOn"] = "The end date must not be before the start date."

    if errors:
        return jsonify({"error": "Some details need fixing.",
                        "fields": errors}), 400

    delegation = ApprovalDelegation(
        organization_id=organization.id,
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        starts_on=starts_on,
        ends_on=ends_on,
        reason=(body.get("reason") or "").strip()[:500] or None,
        created_by_user_id=g.user.id,
    )
    db.session.add(delegation)
    db.session.commit()
    labels = _labels_for({from_user_id, to_user_id})
    return jsonify({"delegation": delegation.public(labels=labels)}), 201


@approval_bp.delete("/delegations/<delegation_id>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_READ)
def end_delegation(delegation_id):
    """End a delegation. Kept as a record rather than deleted."""
    row = scoped(ApprovalDelegation).filter(
        ApprovalDelegation.id == delegation_id
    ).first()
    if row is None:
        return jsonify({"error": "Delegation not found."}), 404
    if row.from_user_id != g.user.id and not has_permission(ORG_SETTINGS):
        return jsonify({"error": "You can only end your own delegations.",
                        "code": "FORBIDDEN"}), 403

    row.active = False
    row.ends_on = row.ends_on or datetime.utcnow().date().isoformat()
    db.session.commit()
    labels = _labels_for({row.from_user_id, row.to_user_id})
    return jsonify({"delegation": row.public(labels=labels)})


# ─── Starting a request from a document ──────────────────────────────────────
def request_for_purchase_order(po: PurchaseOrder, user_id: str):
    """Build the approval chain for a submitted order, if a rule applies.

    Called by the purchase-order submit endpoint. Returns None when no rule
    matches, and the caller keeps its existing single-approval behaviour.
    """
    return start_request(
        organization_id=po.organization_id,
        subject_type=ApprovalRule.PURCHASE_ORDER,
        subject_id=po.id,
        facts=_facts_for_po(po),
        user_id=user_id,
    )


def open_request_payload(organization_id: str, subject_type: str,
                         subject_id: str) -> dict | None:
    """A compact view of a document's live approval, for its detail page."""
    req = open_request_for(organization_id, subject_type, subject_id)
    if req is None:
        return None
    labels = _request_labels(req)
    return {
        "id": req.id,
        "status": req.status,
        "currentLevel": req.current_level,
        "ruleName": req.rule_name,
        "waitingOn": [labels.get(uid) for uid in waiting_on(req)],
        "canAct": step_for_actor(req, g.user.id) is not None,
        "stuck": chain_is_broken(req),
        "steps": [step.public(labels=labels) for step in req.steps],
    }


__all__ = [
    "approval_bp",
    "may_act_for",
    "open_request_payload",
    "request_for_purchase_order",
]
