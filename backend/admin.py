"""Flask-Admin dashboard at /admin (a Django-admin-style CRUD over the models).

Protected by HTTP Basic Auth using ADMIN_USER / ADMIN_PASSWORD. Basic Auth is
used (rather than the app's JWT) because /admin is server-rendered HTML opened
directly in the browser, which can't attach the JWT header. Disabled entirely
when either credential is unset.

Beyond CRUD it adds:
  - a stats dashboard on the index (users, plans, extractions, revenue),
  - a "Compose email" view (/admin/email) to send a branded message to an
    audience (all users / by plan / specific addresses),
  - bulk actions on the User list (send welcome email, change plan).
"""
import hmac

from flask import Response, flash, redirect, request, url_for
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.actions import action
from flask_admin.contrib.sqla import ModelView
from markupsafe import Markup
from sqlalchemy import func

import emails
from config import Config
from extensions import db
from models import ApiKey, Extraction, Payment, User, Webhook

PLAN_CHOICES = ("free", "starter", "pro", "business")


def _authorized() -> bool:
    auth = request.authorization
    if not auth:
        return False
    user_ok = hmac.compare_digest(auth.username or "", Config.ADMIN_USER)
    pass_ok = hmac.compare_digest(auth.password or "", Config.ADMIN_PASSWORD)
    return user_ok and pass_ok


def _challenge() -> Response:
    return Response(
        "Authentication required.",
        401,
        {"WWW-Authenticate": 'Basic realm="InvoiceParsed Admin"'},
    )


class _AuthMixin:
    def is_accessible(self):
        return _authorized()

    def inaccessible_callback(self, name, **kwargs):
        return _challenge()


class SecureIndexView(_AuthMixin, AdminIndexView):
    @expose("/")
    def index(self):
        if not _authorized():
            return _challenge()
        return self.render("admin/dashboard.html", stats=_dashboard_stats())


class SecureModelView(_AuthMixin, ModelView):
    can_view_details = True
    page_size = 50


# ─── Dashboard stats ─────────────────────────────────────────────────────────
def _dashboard_stats() -> dict:
    """Aggregate headline numbers for the admin home page."""
    plan_counts = dict(
        db.session.query(User.plan, func.count(User.id)).group_by(User.plan).all()
    )
    # Sum successful payments (amounts are stored in cents); expose major units.
    revenue_cents = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.status == "succeeded")
        .scalar()
        or 0
    )
    return {
        "total_users": db.session.query(func.count(User.id)).scalar() or 0,
        "verified_users": db.session.query(func.count(User.id))
        .filter(User.email_verified.is_(True))
        .scalar()
        or 0,
        "paying_users": sum(v for k, v in plan_counts.items() if k and k != "free"),
        "plan_counts": {p: plan_counts.get(p, 0) for p in PLAN_CHOICES},
        "total_extractions": db.session.query(func.count(Extraction.id)).scalar() or 0,
        "revenue": revenue_cents / 100,
        "recent_users": (
            User.query.order_by(User.created_at.desc()).limit(8).all()
        ),
    }


# ─── Email composer ──────────────────────────────────────────────────────────
class EmailComposeView(_AuthMixin, BaseView):
    """Compose and send a branded email to a chosen audience."""

    @expose("/", methods=("GET", "POST"))
    def index(self):
        if not _authorized():
            return _challenge()

        result = None
        if request.method == "POST":
            audience = request.form.get("audience", "all")
            plan = request.form.get("plan", "")
            addresses = request.form.get("addresses", "")
            subject = (request.form.get("subject") or "").strip()
            heading = (request.form.get("heading") or "").strip() or subject
            message = request.form.get("message") or ""

            recipients = self._resolve_recipients(audience, plan, addresses)
            if not subject or not message.strip():
                flash("Subject and message are both required.", "error")
            elif not recipients:
                flash("No recipients matched your selection.", "error")
            else:
                body_html = emails.text_to_html(message)
                sent = sum(
                    1
                    for email in recipients
                    if emails.send_custom(email, subject, heading, body_html)
                )
                result = {"attempted": len(recipients), "sent": sent}
                flash(f"Sent {sent} of {len(recipients)} email(s).", "success")

        return self.render(
            "admin/compose_email.html",
            plans=PLAN_CHOICES,
            result=result,
        )

    @staticmethod
    def _resolve_recipients(audience: str, plan: str, addresses: str) -> list[str]:
        if audience == "addresses":
            raw = addresses.replace(",", "\n").split("\n")
            return [a.strip() for a in raw if a.strip()]
        query = User.query.filter(User.email_verified.is_(True))
        if audience == "plan" and plan in PLAN_CHOICES:
            query = query.filter(User.plan == plan)
        return [u.email for u in query.all() if u.email]


# ─── Model views ─────────────────────────────────────────────────────────────
class UserAdmin(SecureModelView):
    column_list = ("email", "name", "plan", "email_verified", "created_at")
    column_searchable_list = ("email", "name")
    column_filters = ("plan", "email_verified")
    column_default_sort = ("created_at", True)
    # Never expose secrets / let them be edited blindly.
    column_exclude_list = ("password_hash", "google_sub")
    form_excluded_columns = ("password_hash", "google_sub", "extractions", "api_keys", "webhooks")
    can_create = False  # accounts are created via signup

    @action("send_welcome", "Send welcome email",
            "Send the welcome email to the selected user(s)?")
    def action_send_welcome(self, ids):
        users = User.query.filter(User.id.in_(ids)).all()
        sent = sum(1 for u in users if emails.send_welcome(u.email, u.name))
        flash(f"Welcome email sent to {sent} of {len(users)} user(s).")

    def _set_plan(self, ids, plan):
        users = User.query.filter(User.id.in_(ids)).all()
        for u in users:
            u.plan = plan
        db.session.commit()
        for u in users:
            emails.send_plan_changed(u.email, plan, u.name)
        flash(f"Set {len(users)} user(s) to the {plan} plan (notification sent).")

    @action("plan_free", "Change plan → free")
    def action_plan_free(self, ids):
        self._set_plan(ids, "free")

    @action("plan_starter", "Change plan → starter")
    def action_plan_starter(self, ids):
        self._set_plan(ids, "starter")

    @action("plan_pro", "Change plan → pro")
    def action_plan_pro(self, ids):
        self._set_plan(ids, "pro")


class ExtractionAdmin(SecureModelView):
    column_list = ("doc_type", "vendor_name", "invoice_number", "total", "currency", "status", "created_at")
    column_searchable_list = ("vendor_name", "invoice_number")
    column_filters = ("doc_type", "status", "currency")
    column_default_sort = ("created_at", True)
    can_create = False


class ApiKeyAdmin(SecureModelView):
    column_list = ("prefix", "name", "user_id", "last_used_at", "created_at")
    column_exclude_list = ("key_hash",)
    can_create = False
    can_edit = False


class WebhookAdmin(SecureModelView):
    column_list = ("url", "active", "last_status", "last_delivery_at", "user_id", "created_at")
    column_filters = ("active",)


class PaymentAdmin(SecureModelView):
    column_list = ("created_at", "user_id", "plan", "amount", "currency", "status", "event_type", "provider_payment_id")
    column_filters = ("plan", "status", "event_type")
    column_searchable_list = ("provider_payment_id", "user_id")
    column_default_sort = ("created_at", True)
    can_create = False
    can_edit = False


def init_admin(app) -> None:
    """Attach the admin to the app if credentials are configured."""
    if not (Config.ADMIN_USER and Config.ADMIN_PASSWORD):
        return
    admin = Admin(
        app,
        name="InvoiceParsed",
        index_view=SecureIndexView(url="/admin"),
    )
    admin.add_view(UserAdmin(User, db.session))
    admin.add_view(ExtractionAdmin(Extraction, db.session))
    admin.add_view(ApiKeyAdmin(ApiKey, db.session))
    admin.add_view(WebhookAdmin(Webhook, db.session))
    admin.add_view(PaymentAdmin(Payment, db.session))
    admin.add_view(EmailComposeView(name="Compose email", endpoint="email"))
