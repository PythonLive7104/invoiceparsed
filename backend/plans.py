"""Plan definitions, free-tier limits, and monthly usage calculation.

The `features` lists here are marketing copy and are NOT served to any
client; the pricing page and the in-app billing page both read
frontend/src/lib/plans.js, which is prerendered at build time. They are kept
identical to that file anyway, so the two never describe the same plan two
different ways. What IS enforced from this file is the capability flags, via
`plan_allows` and `capabilities`.
"""
from datetime import datetime

PLANS = {
    "free": {
        "id": "free",
        "name": "Free",
        "price": 0,
        "limit": 5,  # invoices / month; None means unlimited
        "tagline": "Kick the tires. No credit card required.",
        # Which audience track this plan appears under: personal | business | both
        "segment": "personal",
        # Premium capability flags (gated server-side).
        "batch": False,
        "multiPage": False,
        "api": False,
        "webhooks": False,
        "statements": False,
        "payables": False,
        "features": [
            "5 invoices / month",
            "PDF & image upload",
            "Excel, CSV & JSON export",
            "Extraction history",
        ],
    },
    "starter": {
        "id": "starter",
        "name": "Starter",
        "price": 19,
        "limit": 100,
        "tagline": "For freelancers drowning in client invoices.",
        "highlighted": True,
        "segment": "both",
        "batch": True,
        "multiPage": True,
        "api": False,
        "webhooks": False,
        "statements": False,
        "payables": False,
        "features": [
            "100 invoices / month",
            "Multi-file batch upload",
            "Multi-page invoices",
            "Excel, CSV & JSON export",
            "Email support",
        ],
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "price": 49,
        "limit": None,
        "tagline": "For agencies and developers who automate.",
        "segment": "both",
        "batch": True,
        "multiPage": True,
        "api": True,
        "webhooks": True,
        "statements": False,
        "payables": True,
        "features": [
            "Everything in Starter",
            "Unlimited invoices & receipts",
            "Suppliers, purchase orders & invoice matching",
            "Approvals with roles & permissions",
            "REST API access + webhooks",
        ],
    },
    "business": {
        "id": "business",
        "name": "Business",
        "price": 99,
        "limit": None,
        "tagline": "For teams and high-volume finance ops.",
        "segment": "business",
        "batch": True,
        "multiPage": True,
        "api": True,
        "webhooks": True,
        "statements": True,
        "payables": True,
        # Bank statements are far costlier to extract than invoices/receipts, so
        # they get their own monthly allowance even though invoices/receipts are
        # unlimited. None would mean unlimited statements.
        "statementLimit": 200,
        "features": [
            "Everything in Pro",
            "Unlimited invoices & receipts",
            "200 bank statements / month",
            "Centralized billing & invoicing",
            "Priority support + onboarding",
        ],
    },
}

# Capabilities exposed to clients / used for server-side gating.
#
# `payables` covers the whole accounts-payable module: suppliers, purchase
# orders and invoice-to-PO matching. One flag rather than three, because they
# are not separable - a purchase order is worthless without a supplier to order
# from, and matching is worthless without orders to match against. Selling
# them apart would mean selling two thirds of a workflow.
CAPABILITIES = ("batch", "multiPage", "api", "webhooks", "statements", "payables")

PLAN_ORDER = ["free", "starter", "pro", "business"]

# The payables paywall, named once. Three route modules enforce it, and
# three slightly different descriptions of the same boundary is how a
# product ends up telling customers two different things.
PAYABLES = "payables"
PAYABLES_FEATURE = "Suppliers, purchase orders and invoice matching"



def get_plan(plan_id: str) -> dict:
    return PLANS.get(plan_id, PLANS["free"])


def plan_allows(plan_id: str, capability: str) -> bool:
    return bool(get_plan(plan_id).get(capability, False))


def capabilities(plan_id: str) -> dict:
    plan = get_plan(plan_id)
    return {cap: bool(plan.get(cap, False)) for cap in CAPABILITIES}


def start_of_month(now: datetime | None = None) -> datetime:
    now = now or datetime.utcnow()
    return datetime(now.year, now.month, 1)


def build_statement_usage(statement_used: int, plan_id: str) -> dict:
    """Bank-statement allowance summary. `allowed` is False for plans without the
    statements capability; `limit` of None means unlimited statements."""
    plan = get_plan(plan_id)
    allowed = bool(plan.get("statements", False))
    limit = plan.get("statementLimit") if allowed else None
    unlimited = limit is None
    remaining = None if (not allowed or unlimited) else max(0, limit - statement_used)
    at_limit = bool(allowed and not unlimited and statement_used >= limit)
    return {
        "allowed": allowed,
        "used": statement_used,
        "limit": limit,
        "remaining": remaining,
        "atLimit": at_limit,
    }


def build_usage(used: int, plan_id: str, statement_used: int = 0) -> dict:
    """Build the usage summary returned to the frontend."""
    plan = get_plan(plan_id)
    limit = plan["limit"]
    unlimited = limit is None
    remaining = None if unlimited else max(0, limit - used)
    at_limit = (not unlimited) and used >= limit
    return {
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "plan": plan["id"],
        "planName": plan["name"],
        "periodStart": start_of_month().isoformat() + "Z",
        "atLimit": at_limit,
        "capabilities": {cap: bool(plan.get(cap, False)) for cap in CAPABILITIES},
        "statements": build_statement_usage(statement_used, plan_id),
    }
