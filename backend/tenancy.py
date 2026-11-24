"""Tenant resolution and scoping.

Every tenant-owned row carries an `organization_id`. The danger with that shape
is a forgotten filter: one route that queries `Extraction.query.filter_by(id=...)`
without the organization becomes a cross-tenant data leak, and it looks exactly
like correct code. So routes do not write their own scoping — they call
`scoped(Model)`, which cannot produce an unscoped query.

Resolution order for "which organization is this request acting as":

1. An `X-Organization-Id` header, validated against the caller's memberships.
   A header naming an organization the caller does not belong to is a 403, not a
   silent fall back to their own — falling back would make a probe look like it
   succeeded.
2. An API key's own organization, since keys are issued per organization.
3. The caller's personal organization, then their oldest membership.

`g.organization` and `g.membership` are set by the auth decorators, so handlers
can rely on them being present.
"""
from functools import wraps

from flask import g, jsonify, request

from extensions import db
from models import Organization, OrganizationMembership
from plans import get_plan, plan_allows
from roles import DEFAULT_ROLE, role_allows

ORG_HEADER = "X-Organization-Id"


class TenantError(Exception):
    """Raised when a request cannot be attributed to an organization."""


# ─── Resolution ──────────────────────────────────────────────────────────────
def memberships_for(user) -> list:
    return (
        OrganizationMembership.query.filter_by(user_id=user.id)
        .order_by(OrganizationMembership.created_at.asc())
        .all()
    )


def default_membership(user):
    """The membership to act as when the request does not say.

    Prefers the personal organization: it is the one that holds a solo user's
    own data, so defaulting there keeps single-person accounts behaving exactly
    as they did before tenancy existed.
    """
    rows = memberships_for(user)
    if not rows:
        return None
    for row in rows:
        org = Organization.query.get(row.organization_id)
        if org is not None and org.is_personal:
            return row
    return rows[0]


def resolve_membership(user, requested_org_id: str | None):
    """Which membership this request acts under.

    Raises TenantError if an organization was named that the caller is not a
    member of.
    """
    if requested_org_id:
        row = OrganizationMembership.query.filter_by(
            user_id=user.id, organization_id=requested_org_id
        ).first()
        if row is None:
            raise TenantError("You are not a member of that organization.")
        return row
    return default_membership(user)


def attach_organization(user, requested_org_id: str | None = None) -> None:
    """Set g.organization and g.membership for this request."""
    membership = resolve_membership(user, requested_org_id)
    if membership is None:
        # Every account gets a personal organization at sign-up, so this means
        # an account that predates tenancy and was not backfilled. Repair it
        # rather than failing the request, so a stale row cannot lock someone
        # out of their own data.
        organization = ensure_personal_organization(user)
        membership = OrganizationMembership.query.filter_by(
            user_id=user.id, organization_id=organization.id
        ).first()
    g.membership = membership
    g.organization = Organization.query.get(membership.organization_id)


def organization_id_from_request() -> str | None:
    value = request.headers.get(ORG_HEADER)
    return value.strip() if value and value.strip() else None


def ensure_personal_organization(user, *, name: str | None = None, plan: str = "free"):
    """Create (or return) the user's personal organization, with them as owner.

    Idempotent, so it is safe to call on every sign-up path and from the
    tenancy backfill.
    """
    from roles import OWNER

    existing = (
        Organization.query.join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Organization.id,
        )
        .filter(
            OrganizationMembership.user_id == user.id,
            Organization.is_personal.is_(True),
        )
        .first()
    )
    if existing is not None:
        return existing

    organization = Organization(
        name=name or _personal_name(user),
        is_personal=True,
        plan=plan,
    )
    db.session.add(organization)
    db.session.flush()  # need the id for the membership
    db.session.add(OrganizationMembership(
        organization_id=organization.id, user_id=user.id, role=OWNER,
    ))
    return organization


def _personal_name(user) -> str:
    if user.name:
        return f"{user.name}'s workspace"
    local = (user.email or "account").split("@")[0]
    return f"{local}'s workspace"


def add_member(organization, user, role: str = DEFAULT_ROLE):
    """Add `user` to `organization`, or return the existing membership."""
    existing = OrganizationMembership.query.filter_by(
        organization_id=organization.id, user_id=user.id
    ).first()
    if existing is not None:
        return existing
    membership = OrganizationMembership(
        organization_id=organization.id, user_id=user.id, role=role,
    )
    db.session.add(membership)
    return membership


# ─── Scoping ─────────────────────────────────────────────────────────────────
def scoped(model, organization_id: str | None = None):
    """A query for `model` restricted to the acting organization.

    The single place tenant filtering happens. Routes use this instead of
    `model.query`, so a cross-tenant read needs a deliberate change here rather
    than a forgotten `filter_by` somewhere else.
    """
    org_id = organization_id or getattr(getattr(g, "organization", None), "id", None)
    if not org_id:
        # Fail closed. Returning an unfiltered query here would turn a missing
        # organization into "every tenant's rows".
        raise TenantError("No organization is attached to this request.")
    return model.query.filter(model.organization_id == org_id)


def current_organization():
    return getattr(g, "organization", None)


def current_plan() -> str:
    organization = current_organization()
    return organization.plan if organization is not None else "free"


def current_role() -> str | None:
    membership = getattr(g, "membership", None)
    return membership.role if membership is not None else None


# ─── Permission enforcement ──────────────────────────────────────────────────
def has_permission(permission: str) -> bool:
    role = current_role()
    return bool(role) and role_allows(role, permission)


def require_capability(capability: str, feature: str):
    """Refuse the request unless the acting organization's PLAN includes
    `capability`.

    Distinct from `require_permission`, and both can apply to one route,
    because they answer different questions: a permission is "may this person
    do this", a capability is "has this organization bought this". The error
    codes differ for the same reason - a 403 tells you to ask an administrator,
    a 402 tells you to upgrade, and sending one when you meant the other
    sends people to the wrong place.

    Applied as a per-view decorator rather than a blueprint `before_request`
    hook: the hook would run before the auth decorator had resolved the
    organization, so it would always see the free-plan default and gate
    everybody.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            plan = current_plan()
            if not plan_allows(plan, capability):
                lowest = _lowest_plan_with(capability)
                return (
                    jsonify({
                        "error": (
                            f"{feature} is included on the "
                            f"{lowest} plan and above."
                            if lowest else f"{feature} is not available on your plan."
                        ),
                        "code": "UPGRADE_REQUIRED",
                        "capability": capability,
                        "plan": plan,
                    }),
                    402,
                )
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def _lowest_plan_with(capability: str) -> str | None:
    """The cheapest plan that includes `capability`, named in the error.

    Read from the plan table rather than written into each message, so moving a
    capability between plans does not leave the wrong plan name in an error
    somewhere.
    """
    from plans import PLAN_ORDER

    for plan_id in PLAN_ORDER:
        if plan_allows(plan_id, capability):
            return get_plan(plan_id)["name"]
    return None


def require_permission(permission: str):
    """Refuse the request unless the acting membership grants `permission`.

    Applied *below* the auth decorator, so g.membership is already set.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not has_permission(permission):
                return (
                    jsonify({
                        "error": "Your role does not allow this action.",
                        "code": "FORBIDDEN",
                        "required": permission,
                    }),
                    403,
                )
            return fn(*args, **kwargs)

        return wrapper

    return decorator
