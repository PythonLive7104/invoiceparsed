"""Shared monthly usage counting (used by auth, billing and extract routes)."""
from models import Extraction
from plans import build_usage, start_of_month


def count_usage(user_id: str) -> int:
    """All completed extractions (any document type) this month."""
    return (
        Extraction.query.filter(
            Extraction.user_id == user_id,
            Extraction.status == "completed",
            Extraction.created_at >= start_of_month(),
        ).count()
    )


def count_statements(user_id: str) -> int:
    """Completed bank-statement extractions this month (their own allowance)."""
    return (
        Extraction.query.filter(
            Extraction.user_id == user_id,
            Extraction.doc_type == "statement",
            Extraction.status == "completed",
            Extraction.created_at >= start_of_month(),
        ).count()
    )


def usage_for(user) -> dict:
    """Full usage summary for a user: overall + bank-statement allowance."""
    return build_usage(count_usage(user.id), user.plan, count_statements(user.id))
