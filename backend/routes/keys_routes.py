"""API key management (Pro plan). JWT-authenticated — keys are created and
revoked from the dashboard, not via the API itself."""
from flask import Blueprint, g, jsonify, request

from auth import generate_api_key, login_required
from extensions import db
from models import ApiKey
from plans import plan_allows
from roles import API_KEYS_MANAGE
from tenancy import current_organization, require_permission, scoped

keys_bp = Blueprint("keys", __name__, url_prefix="/api/keys")


@keys_bp.get("")
@login_required
def list_keys():
    rows = scoped(ApiKey).order_by(ApiKey.created_at.desc()).all()
    return jsonify({"keys": [k.public() for k in rows]})


@keys_bp.post("")
@login_required
@require_permission(API_KEYS_MANAGE)
def create_key():
    if not plan_allows(current_organization().plan, "api"):
        return jsonify({"error": "API access requires the Pro plan."}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "API key").strip()[:120] or "API key"

    full, prefix, key_hash = generate_api_key()
    # organization_id owns the key; user_id records who minted it.
    key = ApiKey(
        organization_id=current_organization().id,
        user_id=g.user.id,
        name=name,
        prefix=prefix,
        key_hash=key_hash,
    )
    db.session.add(key)
    db.session.commit()

    # The full key is returned exactly once — it is never stored in plaintext.
    return jsonify({"key": full, "apiKey": key.public()})


@keys_bp.delete("/<kid>")
@login_required
@require_permission(API_KEYS_MANAGE)
def revoke_key(kid):
    key = scoped(ApiKey).filter(ApiKey.id == kid).first()
    if key is None:
        return jsonify({"error": "API key not found."}), 404
    db.session.delete(key)
    db.session.commit()
    return jsonify({"success": True})
