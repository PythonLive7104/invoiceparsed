"""Usage and billing endpoints."""
from flask import Blueprint, g, jsonify, request

from auth import login_required
from extensions import db
from models import Extraction, User
from plans import PLANS, build_usage, start_of_month

billing_bp = Blueprint("billing", __name__, url_prefix="/api")


def _count_usage(user: User) -> int:
    return (
        Extraction.query.filter(
            Extraction.user_id == user.id,
            Extraction.status == "completed",
            Extraction.created_at >= start_of_month(),
        ).count()
    )


@billing_bp.get("/usage")
@login_required
def usage():
    return jsonify({"usage": build_usage(_count_usage(g.user), g.user.plan)})


@billing_bp.post("/billing/upgrade")
@login_required
def upgrade():
    """MVP stub. In production this opens a Dodo Payments checkout and the plan
    is updated via webhook on successful payment. For the demo we apply the
    change immediately so the upgrade flow is fully clickable."""
    data = request.get_json(silent=True) or {}
    plan = data.get("plan")
    if plan not in PLANS:
        return jsonify({"error": "Invalid plan."}), 400

    g.user.plan = plan
    db.session.commit()
    return jsonify({"user": g.user.public(), "demo": True})
