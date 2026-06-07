"""InvoiceParsed Flask API — application factory and entrypoint.

Run locally:
    cd backend
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    flask --app app run --debug        # or: python app.py
"""
import os

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from extensions import db, limiter
from plans import PLANS, PLAN_ORDER
from routes import auth_bp, billing_bp, extract_bp, keys_bp, webhook_bp


def _init_sentry(config_class) -> None:
    """Start Sentry error monitoring if a DSN is configured (no-op otherwise)."""
    dsn = getattr(config_class, "SENTRY_DSN", "")
    if not dsn:
        return
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    sentry_sdk.init(
        dsn=dsn,
        integrations=[FlaskIntegration()],
        environment=getattr(config_class, "SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=getattr(config_class, "SENTRY_TRACES_SAMPLE_RATE", 0.0),
        send_default_pii=False,  # don't ship user emails/IPs to Sentry
    )


def create_app(config_class=Config) -> Flask:
    _init_sentry(config_class)

    app = Flask(__name__)
    app.config.from_object(config_class)

    # Behind reverse proxies: trust N hops of X-Forwarded-* so request.remote_addr
    # is the real client IP (correct rate-limiting) and URLs use the external
    # scheme/host. 1 = nginx only, 2 = Caddy → nginx (TLS), 0 = none.
    hops = int(app.config.get("PROXY_HOPS", 1))
    if hops:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)

    db.init_app(app)

    # Rate limiting. Config keys (RATELIMIT_*) are read by Flask-Limiter directly.
    limiter.init_app(app)

    # Allow the React frontend (configurable origins) to call the API.
    origins = [o.strip() for o in app.config["FRONTEND_ORIGIN"].split(",") if o.strip()]
    CORS(app, resources={r"/api/*": {"origins": origins}}, supports_credentials=True)

    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    app.register_blueprint(auth_bp)
    app.register_blueprint(extract_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(keys_bp)
    app.register_blueprint(webhook_bp)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "openai_configured": bool(app.config["OPENAI_API_KEY"])})

    @app.get("/api/plans")
    def plans():
        return jsonify({"plans": PLANS, "order": PLAN_ORDER})

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_e):
        return jsonify({"error": "File exceeds the 10MB limit."}), 413

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({
            "error": "Too many requests. Please slow down and try again shortly.",
            "code": "RATE_LIMITED",
            "detail": str(getattr(e, "description", "")),
        }), 429

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "Not found."}), 404

    with app.app_context():
        db.create_all()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
