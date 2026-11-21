"""Shared monthly usage counting, scoped to the acting organization.

Usage is counted per ORGANIZATION, not per user: a team shares one monthly
allowance. Counting per user would hand every colleague on one subscription
their own quota.
"""
from models import Extraction
from plans import build_usage, start_of_month


def count_usage(organization_id: str) -> int:
    """All completed extractions (any document type) this month."""
    return (
        Extraction.query.filter(
            Extraction.organization_id == organization_id,
            Extraction.status == "completed",
            Extraction.created_at >= start_of_month(),
        ).count()
    )


def count_statements(organization_id: str) -> int:
    """Completed bank-statement extractions this month (their own allowance)."""
    return (
        Extraction.query.filter(
            Extraction.organization_id == organization_id,
            Extraction.doc_type == "statement",
            Extraction.status == "completed",
            Extraction.created_at >= start_of_month(),
        ).count()
    )


def usage_for(organization) -> dict:
    """Full usage summary for an organization: overall + bank-statement allowance."""
    return build_usage(
        count_usage(organization.id), organization.plan, count_statements(organization.id)
    )
