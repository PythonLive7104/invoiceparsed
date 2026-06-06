"""Webhook management (Pro plan). JWT-authenticated."""
import secrets

from flask import Blueprint, g, jsonify, request

from auth import login_required
from extensions import db
from models import Webhook
from plans import plan_allows
from webhooks import deliver

webhook_bp = Blueprint("webhooks", __name__, url_prefix="/api/webhooks")


def _valid_url(url: str) -> bool:
    return isinstance(url, str) and url.startswith(("http://", "https://")) and len(url) <= 2048


@webhook_bp.get("")
@login_required
def list_webhooks():
    rows = (
        Webhook.query.filter_by(user_id=g.user.id)
        .order_by(Webhook.created_at.desc())
        .all()
    )
    return jsonify({"webhooks": [w.public(include_secret=True) for w in rows]})


@webhook_bp.post("")
@login_required
def create_webhook():
    if not plan_allows(g.user.plan, "webhooks"):
        return jsonify({"error": "Webhooks require the Pro plan."}), 403

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not _valid_url(url):
        return jsonify({"error": "Enter a valid http(s) URL."}), 400

    hook = Webhook(user_id=g.user.id, url=url, secret="whsec_" + secrets.token_urlsafe(24))
    db.session.add(hook)
    db.session.commit()
    return jsonify({"webhook": hook.public(include_secret=True)})


@webhook_bp.delete("/<wid>")
@login_required
def delete_webhook(wid):
    hook = Webhook.query.filter_by(id=wid, user_id=g.user.id).first()
    if hook is None:
        return jsonify({"error": "Webhook not found."}), 404
    db.session.delete(hook)
    db.session.commit()
    return jsonify({"success": True})


@webhook_bp.post("/<wid>/test")
@login_required
def test_webhook(wid):
    hook = Webhook.query.filter_by(id=wid, user_id=g.user.id).first()
    if hook is None:
        return jsonify({"error": "Webhook not found."}), 404

    status = deliver(
        hook,
        "ping",
        {"message": "Test event from InvoiceParsed", "webhookId": hook.id},
    )
    return jsonify({"delivered": 200 <= status < 300, "status": status})
