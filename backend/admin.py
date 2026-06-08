"""Flask-Admin dashboard at /admin (a Django-admin-style CRUD over the models).

Protected by HTTP Basic Auth using ADMIN_USER / ADMIN_PASSWORD. Basic Auth is
used (rather than the app's JWT) because /admin is server-rendered HTML opened
directly in the browser, which can't attach the JWT header. Disabled entirely
when either credential is unset.
"""
import hmac

from flask import Response, request
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView

from config import Config
from extensions import db
from models import ApiKey, Extraction, User, Webhook


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
        return super().index()


class SecureModelView(_AuthMixin, ModelView):
    can_view_details = True
    page_size = 50


class UserAdmin(SecureModelView):
    column_list = ("email", "name", "plan", "email_verified", "created_at")
    column_searchable_list = ("email", "name")
    column_filters = ("plan", "email_verified")
    column_default_sort = ("created_at", True)
    # Never expose secrets / let them be edited blindly.
    column_exclude_list = ("password_hash", "google_sub")
    form_excluded_columns = ("password_hash", "google_sub", "extractions", "api_keys", "webhooks")
    can_create = False  # accounts are created via signup


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
