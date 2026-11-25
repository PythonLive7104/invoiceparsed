"""Approval workflow: rule matching, chain building, and decisions.

Configuration, not code. Every organization draws its authorization lines in a
different place, and a threshold baked into a deployment is one that gets
changed by a developer at the worst possible moment.

Five rules shape everything below.

1. **One rule applies, not all of them.** The highest-priority matching rule
   wins. Combining every match would produce approval chains nobody can
   predict or explain, and a chain you cannot explain is one people route
   around.

2. **The chain is materialized at submission.** Editing a rule must not
   rewrite an approval already in flight. The people who signed it signed a
   specific chain, and an audit trail that changes shape retrospectively is
   not an audit trail.

3. **Levels are sequential; approvers within a level are not.** Level 2 is not
   asked until level 1 is satisfied, so a director is not troubled by
   something their manager is going to reject. Within a level everyone is
   asked at once, and `require_all` decides whether every one must sign or any
   one is enough.

4. **You cannot approve your own submission.** The oldest internal control
   there is, and it is enforced here as well as on the purchase order itself —
   with the same escape hatch, because an organization where the submitter is
   the only possible approver needs approval to be possible rather than
   merely safe.

5. **Nothing is silently skipped.** Where a step cannot be satisfied — a role
   nobody holds, an approver who has left — the request stops and says so
   rather than quietly treating the level as met.
"""
import logging
from datetime import date, datetime

from extensions import db
from models import (
    ApprovalDelegation,
    ApprovalEvent,
    ApprovalRequest,
    ApprovalRequestStep,
    ApprovalRule,
    ApprovalRuleStep,
    OrganizationMembership,
)
from money import to_decimal
from roles import APPROVALS_ACT, role_allows

logger = logging.getLogger(__name__)

MAX_LEVELS = 10
MAX_STEPS_PER_LEVEL = 20
MAX_COMMENT = 1000


class ApprovalError(Exception):
    """An approval action the rules do not allow, with a code for the client."""

    def __init__(self, message: str, code: str = "INVALID_APPROVAL"):
        super().__init__(message)
        self.message = message
        self.code = code


# ─── Matching ────────────────────────────────────────────────────────────────
def _text_matches(condition, value) -> bool:
    """A text condition matches case-insensitively, trimmed.

    An unset condition does not constrain, which is what makes a rule with no
    conditions mean "everything".
    """
    if condition in (None, ""):
        return True
    return (value or "").strip().lower() == condition.strip().lower()


def rule_matches(rule: ApprovalRule, facts: dict) -> bool:
    """Does `facts` satisfy every condition on `rule`?

    `facts` carries amount, currency, department, costCenter, project,
    category and supplierId — whatever the subject has. A fact the subject
    does not carry is None, and only constrains if the rule asks for it.
    """
    amount = to_decimal(facts.get("amount"))
    minimum = to_decimal(rule.min_amount)
    maximum = to_decimal(rule.max_amount)

    # An amount we could not read FAILS a bound rather than passing it: an
    # unreadable total must not slip under a threshold and skip approval.
    if minimum is not None and (amount is None or amount < minimum):
        return False
    if maximum is not None and (amount is None or amount > maximum):
        return False

    for condition, value in (
        (rule.currency, facts.get("currency")),
        (rule.department, facts.get("department")),
        (rule.cost_center, facts.get("costCenter")),
        (rule.project, facts.get("project")),
        (rule.category, facts.get("category")),
    ):
        if not _text_matches(condition, value):
            return False

    return not (rule.supplier_id and rule.supplier_id != facts.get("supplierId"))


def find_rule(organization_id: str, subject_type: str, facts: dict):
    """The rule that governs this document, or None.

    Ordered by priority then creation, so a rule added later never silently
    displaces an existing one of equal priority.
    """
    rules = (
        ApprovalRule.query.filter_by(
            organization_id=organization_id,
            subject_type=subject_type,
            active=True,
        )
        .order_by(ApprovalRule.priority.desc(), ApprovalRule.created_at.asc())
        .all()
    )
    for rule in rules:
        if rule_matches(rule, facts):
            return rule
    return None


# ─── Resolving approvers ─────────────────────────────────────────────────────
def members_with_role(organization_id: str, role: str) -> list[str]:
    rows = (
        db.session.query(OrganizationMembership.user_id)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.role == role,
        )
        .all()
    )
    return [row[0] for row in rows]


def members_who_can_approve(organization_id: str) -> list[str]:
    """Everyone whose role grants `approvals:act`."""
    rows = (
        db.session.query(OrganizationMembership.user_id,
                         OrganizationMembership.role)
        .filter(OrganizationMembership.organization_id == organization_id)
        .all()
    )
    return [user_id for user_id, role in rows if role_allows(role, APPROVALS_ACT)]


def _resolve_step(step: ApprovalRuleStep, organization_id: str) -> list[tuple]:
    """(user_id, role) pairs this rule step resolves to.

    A role resolves to every member holding it. Empty is a real answer and the
    caller treats it as a broken chain rather than a satisfied one.
    """
    if step.approver_type == ApprovalRuleStep.BY_USER and step.approver_user_id:
        member = OrganizationMembership.query.filter_by(
            organization_id=organization_id, user_id=step.approver_user_id
        ).first()
        if member is None:
            return []
        return [(step.approver_user_id, member.role)]

    if step.approver_role:
        return [
            (user_id, step.approver_role)
            for user_id in members_with_role(organization_id, step.approver_role)
        ]
    return []


# ─── Delegation ──────────────────────────────────────────────────────────────
def _today() -> str:
    return date.today().isoformat()


def active_delegations(organization_id: str, to_user_id: str) -> list:
    """Delegations currently letting `to_user_id` act for somebody else.

    Date-bounded, inclusive, and an unset bound is open on that side. Resolved
    now rather than when the chain was built, because going away *after* a
    request was raised is the case that actually happens.
    """
    today = _today()
    rows = ApprovalDelegation.query.filter_by(
        organization_id=organization_id, to_user_id=to_user_id, active=True
    ).all()
    live = []
    for row in rows:
        if row.starts_on and row.starts_on > today:
            continue
        if row.ends_on and row.ends_on < today:
            continue
        live.append(row)
    return live


def may_act_for(organization_id: str, actor_user_id: str,
                approver_user_id: str) -> bool:
    if actor_user_id == approver_user_id:
        return True
    return any(
        delegation.from_user_id == approver_user_id
        for delegation in active_delegations(organization_id, actor_user_id)
    )


# ─── Building a request ──────────────────────────────────────────────────────
def _event(request: ApprovalRequest, action: str, *, user_id=None,
           target_user_id=None, level=None, comment=None) -> ApprovalEvent:
    event = ApprovalEvent(
        request_id=request.id,
        organization_id=request.organization_id,
        action=action,
        user_id=user_id,
        target_user_id=target_user_id,
        level=level,
        comment=(comment or None),
    )
    db.session.add(event)
    return event


def open_request_for(organization_id: str, subject_type: str, subject_id: str):
    """The live approval request for a document, if there is one."""
    return (
        ApprovalRequest.query.filter(
            ApprovalRequest.organization_id == organization_id,
            ApprovalRequest.subject_type == subject_type,
            ApprovalRequest.subject_id == subject_id,
            ApprovalRequest.status.in_(ApprovalRequest.OPEN_STATUSES),
        )
        .order_by(ApprovalRequest.submitted_at.desc())
        .first()
    )


def start_request(*, organization_id: str, subject_type: str, subject_id: str,
                  facts: dict, user_id: str | None) -> ApprovalRequest | None:
    """Build an approval chain for a document, or None if no rule applies.

    Returning None is not a failure: it means this organization has not asked
    for a workflow here, and the caller falls back to whatever single-step
    approval it had before. That is what keeps the feature additive for
    everyone who has not configured it.
    """
    existing = open_request_for(organization_id, subject_type, subject_id)
    if existing is not None:
        return existing

    rule = find_rule(organization_id, subject_type, facts)
    if rule is None or not rule.steps:
        return None

    request = ApprovalRequest(
        organization_id=organization_id,
        subject_type=subject_type,
        subject_id=subject_id,
        rule_id=rule.id,
        rule_name=rule.name,
        status=ApprovalRequest.PENDING,
        amount=to_decimal(facts.get("amount")),
        currency=facts.get("currency"),
        submitted_by_user_id=user_id,
    )
    db.session.add(request)
    db.session.flush()

    levels = sorted({step.level for step in rule.steps})[:MAX_LEVELS]
    for level in levels:
        for rule_step in [s for s in rule.steps if s.level == level]:
            resolved = _resolve_step(rule_step, organization_id)[:MAX_STEPS_PER_LEVEL]
            for approver_id, role in resolved:
                db.session.add(ApprovalRequestStep(
                    request_id=request.id,
                    organization_id=organization_id,
                    level=level,
                    approver_user_id=approver_id,
                    approver_role=role,
                    require_all=bool(rule_step.require_all),
                ))

    request.current_level = levels[0] if levels else 1
    _event(request, ApprovalEvent.SUBMITTED, user_id=user_id,
           level=request.current_level, comment=f"Rule: {rule.name}")
    db.session.flush()
    return request


# ─── Decisions ───────────────────────────────────────────────────────────────
def pending_steps_at(request: ApprovalRequest, level: int) -> list:
    return [
        step for step in request.steps
        if step.level == level and step.status == ApprovalRequestStep.PENDING
    ]


def steps_at(request: ApprovalRequest, level: int) -> list:
    return [step for step in request.steps if step.level == level]


def levels_of(request: ApprovalRequest) -> list[int]:
    return sorted({step.level for step in request.steps})


def step_for_actor(request: ApprovalRequest, actor_user_id: str):
    """The step this person may act on at the current level, or None.

    Their own step first; a step they hold a delegation for otherwise. Their
    own takes precedence so that someone who is both an approver and a
    delegate signs as themselves.
    """
    candidates = pending_steps_at(request, request.current_level)
    for step in candidates:
        if step.approver_user_id == actor_user_id:
            return step
    for step in candidates:
        if may_act_for(request.organization_id, actor_user_id,
                       step.approver_user_id):
            return step
    return None


def _level_satisfied(request: ApprovalRequest, level: int) -> bool:
    """Is this level done?

    `require_all` on any step at the level means every approver must sign.
    Otherwise one approval is enough and the rest are marked skipped — they
    are not outstanding work, and leaving them pending would keep the request
    in somebody's queue forever.
    """
    level_steps = steps_at(request, level)
    if not level_steps:
        return False
    require_all = any(step.require_all for step in level_steps)
    approved = [s for s in level_steps
                if s.status == ApprovalRequestStep.APPROVED]
    if require_all:
        return len(approved) == len(level_steps)
    return len(approved) >= 1


def _advance(request: ApprovalRequest) -> None:
    """Move to the next level, or complete the request."""
    levels = levels_of(request)
    if not _level_satisfied(request, request.current_level):
        return

    for step in pending_steps_at(request, request.current_level):
        step.status = ApprovalRequestStep.SKIPPED
    _event(request, ApprovalEvent.LEVEL_COMPLETED, level=request.current_level)

    later = [level for level in levels if level > request.current_level]
    if later:
        request.current_level = later[0]
        request.status = ApprovalRequest.PENDING
        return

    request.status = ApprovalRequest.APPROVED
    request.completed_at = datetime.utcnow()


def can_decide(request: ApprovalRequest, actor_user_id: str) -> None:
    """Raise unless this person may record a decision right now."""
    if not request.is_open:
        raise ApprovalError(
            f"This request is already {request.status}.", "NOT_OPEN",
        )
    if request.submitted_by_user_id == actor_user_id:
        # Rule 4, with the same escape hatch as the purchase-order rule: in an
        # organization where the submitter is the only possible approver,
        # refusing would make approval impossible rather than safer.
        others = [
            user_id for user_id in members_who_can_approve(request.organization_id)
            if user_id != actor_user_id
        ]
        if others:
            raise ApprovalError(
                "You cannot approve a request you submitted yourself.",
                "SELF_APPROVAL",
            )
    if step_for_actor(request, actor_user_id) is None:
        raise ApprovalError(
            "This request is not waiting on you.", "NOT_YOUR_TURN",
        )


def approve(request: ApprovalRequest, actor_user_id: str, *,
            comment: str | None = None) -> None:
    can_decide(request, actor_user_id)
    step = step_for_actor(request, actor_user_id)
    step.status = ApprovalRequestStep.APPROVED
    step.decided_at = datetime.utcnow()
    step.comment = (comment or None)
    step.acted_by_user_id = actor_user_id

    on_behalf = step.approver_user_id != actor_user_id
    _event(
        request, ApprovalEvent.APPROVED, user_id=actor_user_id,
        target_user_id=step.approver_user_id if on_behalf else None,
        level=step.level, comment=comment,
    )
    request.outcome_comment = (comment or None)
    _advance(request)


def reject(request: ApprovalRequest, actor_user_id: str, *, reason: str) -> None:
    """Reject outright. One rejection ends the request.

    Not "this level failed" but "this document is refused": asking the other
    approvers at the same level to weigh in on something already rejected
    wastes their time and muddies who decided.
    """
    if not (reason or "").strip():
        raise ApprovalError("Say why you are rejecting this.", "REASON_REQUIRED")
    can_decide(request, actor_user_id)
    step = step_for_actor(request, actor_user_id)
    step.status = ApprovalRequestStep.REJECTED
    step.decided_at = datetime.utcnow()
    step.comment = reason[:MAX_COMMENT]
    step.acted_by_user_id = actor_user_id

    for other in pending_steps_at(request, request.current_level):
        if other.id != step.id:
            other.status = ApprovalRequestStep.SKIPPED

    request.status = ApprovalRequest.REJECTED
    request.completed_at = datetime.utcnow()
    request.outcome_comment = reason[:MAX_COMMENT]
    _event(request, ApprovalEvent.REJECTED, user_id=actor_user_id,
           level=step.level, comment=reason)


def request_information(request: ApprovalRequest, actor_user_id: str, *,
                        question: str) -> None:
    """Ask the submitter something without approving or rejecting.

    The request stays assigned where it is — the approver has not handed it
    back, they are waiting — so nothing is lost if the question goes
    unanswered, and the step is still theirs when it is.
    """
    if not (question or "").strip():
        raise ApprovalError("Say what you need to know.", "QUESTION_REQUIRED")
    if not request.is_open:
        raise ApprovalError(f"This request is already {request.status}.", "NOT_OPEN")
    if step_for_actor(request, actor_user_id) is None:
        raise ApprovalError("This request is not waiting on you.", "NOT_YOUR_TURN")

    request.status = ApprovalRequest.INFO_REQUESTED
    _event(request, ApprovalEvent.INFO_REQUESTED, user_id=actor_user_id,
           target_user_id=request.submitted_by_user_id,
           level=request.current_level, comment=question[:MAX_COMMENT])


def provide_information(request: ApprovalRequest, actor_user_id: str, *,
                        answer: str) -> None:
    """Answer an approver's question and put the request back in their queue."""
    if not (answer or "").strip():
        raise ApprovalError("Write an answer.", "ANSWER_REQUIRED")
    if request.status != ApprovalRequest.INFO_REQUESTED:
        raise ApprovalError("Nothing has been asked about this request.",
                            "NOTHING_ASKED")
    request.status = ApprovalRequest.PENDING
    _event(request, ApprovalEvent.INFO_PROVIDED, user_id=actor_user_id,
           level=request.current_level, comment=answer[:MAX_COMMENT])


def cancel(request: ApprovalRequest, actor_user_id: str, *,
           reason: str | None = None) -> None:
    if not request.is_open:
        raise ApprovalError(f"This request is already {request.status}.", "NOT_OPEN")
    request.status = ApprovalRequest.CANCELLED
    request.completed_at = datetime.utcnow()
    request.outcome_comment = (reason or None)
    for step in request.steps:
        if step.status == ApprovalRequestStep.PENDING:
            step.status = ApprovalRequestStep.SKIPPED
    _event(request, ApprovalEvent.CANCELLED, user_id=actor_user_id,
           level=request.current_level, comment=reason)


def record_reminder(request: ApprovalRequest, actor_user_id: str,
                    targets: list[str]) -> None:
    request.last_reminded_at = datetime.utcnow()
    for target in targets:
        _event(request, ApprovalEvent.REMINDED, user_id=actor_user_id,
               target_user_id=target, level=request.current_level)


def waiting_on(request: ApprovalRequest) -> list[str]:
    """User ids the request is currently waiting for."""
    return [
        step.approver_user_id
        for step in pending_steps_at(request, request.current_level)
        if step.approver_user_id
    ]


def chain_is_broken(request: ApprovalRequest) -> bool:
    """Is this request stuck with nobody able to act?

    Rule 5. A level whose approvers have all left, or a role nobody holds,
    leaves a request that can never complete — and a request silently parked
    forever is worse than one that says it is stuck.
    """
    return request.is_open and not pending_steps_at(request, request.current_level)
