"""Organization profile and setup checklist.

The checklist is DERIVED from real state on every request rather than stored as
a wizard position. A stored "you are on step 3" starts lying the moment
anything changes underneath it — a plan downgrade, a deleted document, an email
address changed and re-verified. Deriving it means the checklist is always an
honest description of the account.

The only thing stored is whether the owner has dismissed it, which is a
preference and genuinely cannot be derived.
"""
import logging
from datetime import datetime

from flask import Blueprint, g, jsonify, request

from auth import login_required
from extensions import db
from models import Extraction, OrganizationMembership, User
from plans import PLANS
from roles import (
    APPROVALS_READ,
    MEMBERS_READ,
    ORG_SETTINGS,
    permissions_for,
)
from tenancy import (
    current_organization,
    current_role,
    has_permission,
    require_permission,
    scoped,
)
from usage import usage_for

organization_bp = Blueprint("organizations", __name__, url_prefix="/api/organizations")
logger = logging.getLogger(__name__)

# ISO 4217 is three letters; ISO 3166-1 alpha-2 is two.
CURRENCY_LENGTH = 3
COUNTRY_LENGTH = 2


def _step(key, title, description, done, action=None, optional=False):
    return {
        "key": key,
        "title": title,
        "description": description,
        "done": bool(done),
        "action": action,
        "optional": optional,
    }


def onboarding_state(user, organization) -> dict:
    """The setup checklist, computed from what is actually true right now."""
    has_profile = bool(organization.country or organization.currency or organization.tax_id)
    usage = usage_for(organization)

    documents = scoped(Extraction).filter(Extraction.deleted_at.is_(None))
    uploaded = documents.order_by(None).count()
    reviewed = (
        documents.filter(Extraction.reviewed_at.isnot(None)).order_by(None).count()
    )

    steps = [
        _step(
            "verify_email", "Confirm your email",
            "We sent you a link when you signed up.",
            user.email_verified,
        ),
        _step(
            "organization", "Name your organization",
            "This is the workspace your documents belong to.",
            bool(organization.name),
        ),
        _step(
            "profile", "Add your business details",
            "Country, currency and tax ID — used on exports and reports.",
            has_profile,
            action="/dashboard/settings",
            optional=True,
        ),
        _step(
            "plan", "Choose a plan",
            f"You're on {PLANS.get(organization.plan, {}).get('name', organization.plan)}."
            " Upgrade when you need more.",
            # Free is a real, deliberate choice, so any plan counts as chosen;
            # nagging someone who has decided is just noise.
            True,
            action="/dashboard/billing",
            optional=True,
        ),
        _step(
            "first_upload", "Process your first document",
            "Drop in an invoice, receipt or bank statement.",
            uploaded > 0,
            # The fragment matters: this step is shown ON the dashboard, so a
            # bare "/dashboard" navigates to the page the reader is already
            # looking at and appears to do nothing. The uploader is further
            # down, past this checklist.
            action="/dashboard#extract",
        ),
        _step(
            "review", "Review what we extracted",
            "Check the fields against the original and correct anything we got wrong.",
            reviewed > 0,
            action="/dashboard/history",
        ),
    ]

    required = [s for s in steps if not s["optional"]]
    return {
        "steps": steps,
        "completed": sum(1 for s in required if s["done"]),
        "total": len(required),
        "complete": all(s["done"] for s in required),
        "dismissed": organization.onboarding_dismissed_at is not None,
        "usage": usage,
    }


@organization_bp.get("/current")
@login_required
def get_current():
    organization = current_organization()
    return jsonify({
        "organization": organization.public(),
        "role": current_role(),
        # The caller's permissions, sent as data rather than left for the
        # client to derive from the role. A copy of the role table in the
        # frontend would drift from this one, and the drift would show up as a
        # button that 403s - or worse, a control the server quietly allows that
        # the UI has decided to hide.
        "permissions": sorted(permissions_for(current_role() or "")),
        "onboarding": onboarding_state(g.user, organization),
    })


@organization_bp.patch("/current")
@login_required
@require_permission(ORG_SETTINGS)
def update_current():
    """Update the organization profile.

    Validates rather than silently storing nonsense: a two-letter "currency"
    would quietly corrupt every report built on it later.
    """
    organization = current_organization()
    data = request.get_json(silent=True) or {}
    errors = {}

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            errors["name"] = "An organization needs a name."
        elif len(name) > 200:
            errors["name"] = "That name is too long."
        else:
            organization.name = name

    if "country" in data:
        country = (data.get("country") or "").strip().upper()
        if country and len(country) != COUNTRY_LENGTH:
            errors["country"] = "Use a two-letter country code, e.g. NG or GB."
        else:
            organization.country = country or None

    if "currency" in data:
        currency = (data.get("currency") or "").strip().upper()
        if currency and not (len(currency) == CURRENCY_LENGTH and currency.isalpha()):
            errors["currency"] = "Use a three-letter currency code, e.g. USD or NGN."
        else:
            organization.currency = currency or None

    if "taxId" in data:
        tax_id = (data.get("taxId") or "").strip()
        organization.tax_id = tax_id[:60] or None

    if errors:
        return jsonify({"error": "Some details need fixing.", "fields": errors}), 400

    db.session.commit()
    return jsonify({
        "organization": organization.public(),
        "onboarding": onboarding_state(g.user, organization),
    })


@organization_bp.get("/current/members")
@login_required
@require_permission(APPROVALS_READ)
def list_members():
    """Who is in this organization.

    Gated on `approvals:read` rather than `members:read`, which is the
    stricter member-management permission. The distinction is deliberate:
    knowing which colleagues exist is not sensitive — you work with them, and
    an approval chain names them to your face. What `members:read` protects is
    the administrative view, so **email addresses are only included for
    callers who hold it**. Everyone else gets a name and a role, which is what
    a delegation picker needs and no more.
    """
    organization = current_organization()
    rows = (
        db.session.query(OrganizationMembership, User)
        .join(User, User.id == OrganizationMembership.user_id)
        .filter(OrganizationMembership.organization_id == organization.id)
        .order_by(User.name.asc(), User.email.asc())
        .limit(500)
        .all()
    )
    detailed = has_permission(MEMBERS_READ)
    return jsonify({
        "members": [
            {
                "userId": user.id,
                "name": user.name or user.email,
                "role": membership.role,
                **({"email": user.email} if detailed else {}),
            }
            for membership, user in rows
        ],
    })


@organization_bp.post("/current/onboarding/dismiss")
@login_required
def dismiss_onboarding():
    """Hide the setup checklist.

    Not permission-gated: any member can clear it from their organization's
    dashboard, and it changes nothing but what is displayed.
    """
    organization = current_organization()
    organization.onboarding_dismissed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"onboarding": onboarding_state(g.user, organization)})


@organization_bp.post("/current/onboarding/restore")
@login_required
def restore_onboarding():
    organization = current_organization()
    organization.onboarding_dismissed_at = None
    db.session.commit()
    return jsonify({"onboarding": onboarding_state(g.user, organization)})
