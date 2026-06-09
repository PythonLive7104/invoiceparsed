"""Plan definitions, free-tier limits, and monthly usage calculation."""
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
        "features": [
            "Unlimited invoices",
            "Multi-file batch upload",
            "Multi-page invoices",
            "REST API access",
            "Webhook integrations",
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
        "features": [
            "Everything in Pro",
            "Bank statement extraction",
            "High-volume processing",
            "Centralized billing & invoicing",
            "Priority support + onboarding",
        ],
    },
}

# Capabilities exposed to clients / used for server-side gating.
CAPABILITIES = ("batch", "multiPage", "api", "webhooks", "statements")

PLAN_ORDER = ["free", "starter", "pro", "business"]


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


def build_usage(used: int, plan_id: str) -> dict:
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
    }
