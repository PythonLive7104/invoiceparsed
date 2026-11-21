"""Webhook management (Pro plan). JWT-authenticated."""
import secrets

from flask import Blueprint, g, jsonify, request

from auth import login_required
from extensions import db
from models import Webhook
from plans import plan_allows
from roles import WEBHOOKS_MANAGE
from tenancy import current_organization, require_permission, scoped
from webhooks import UnsafeWebhookUrl, assert_safe_url, deliver

webhook_bp = Blueprint("webhooks", __name__, url_prefix="/api/webhooks")


@webhook_bp.get("")
@login_required
def list_webhooks():
    rows = scoped(Webhook).order_by(Webhook.created_at.desc()).all()
    return jsonify({"webhooks": [w.public(include_secret=True) for w in rows]})


@webhook_bp.post("")
@login_required
@require_permission(WEBHOOKS_MANAGE)
def create_webhook():
    if not plan_allows(current_organization().plan, "webhooks"):
        return jsonify({"error": "Webhooks require the Pro plan."}), 403

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    try:
        assert_safe_url(url)
    except UnsafeWebhookUrl as exc:
        return jsonify({"error": str(exc), "code": "INVALID_WEBHOOK_URL"}), 400

    # organization_id owns the endpoint; user_id records who added it.
    hook = Webhook(
        organization_id=current_organization().id,
        user_id=g.user.id,
        url=url,
        secret="whsec_" + secrets.token_urlsafe(24),
    )
    db.session.add(hook)
    db.session.commit()
    return jsonify({"webhook": hook.public(include_secret=True)})


@webhook_bp.delete("/<wid>")
@login_required
@require_permission(WEBHOOKS_MANAGE)
def delete_webhook(wid):
    hook = scoped(Webhook).filter(Webhook.id == wid).first()
    if hook is None:
        return jsonify({"error": "Webhook not found."}), 404
    db.session.delete(hook)
    db.session.commit()
    return jsonify({"success": True})


@webhook_bp.post("/<wid>/test")
@login_required
@require_permission(WEBHOOKS_MANAGE)
def test_webhook(wid):
    hook = scoped(Webhook).filter(Webhook.id == wid).first()
    if hook is None:
        return jsonify({"error": "Webhook not found."}), 404

    # Single attempt — a manual test shouldn't block the request on retry backoff.
    status = deliver(
        hook,
        "ping",
        {"message": "Test event from InvoiceParsed", "webhookId": hook.id},
        max_attempts=1,
    )
    return jsonify({"delivered": 200 <= status < 300, "status": status})
