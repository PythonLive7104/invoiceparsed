"""SQLAlchemy models: User and Extraction."""
import uuid
from datetime import datetime

from extensions import db


def _uuid() -> str:
    return uuid.uuid4().hex


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=True)
    # Null for accounts created via Google (no local password).
    password_hash = db.Column(db.String(255), nullable=True)
    google_sub = db.Column(db.String(64), unique=True, nullable=True, index=True)
    image = db.Column(db.String(1024), nullable=True)
    plan = db.Column(db.String(20), nullable=False, default="free")  # free|starter|pro
    # Email/password accounts must confirm via emailed link before they get a
    # session. Google accounts are verified by Google, so they start True.
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    extractions = db.relationship(
        "Extraction", backref="user", cascade="all, delete-orphan", lazy="dynamic"
    )
    api_keys = db.relationship(
        "ApiKey", backref="user", cascade="all, delete-orphan", lazy="dynamic"
    )
    webhooks = db.relationship(
        "Webhook", backref="user", cascade="all, delete-orphan", lazy="dynamic"
    )

    def public(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "plan": self.plan,
            "image": self.image,
            "emailVerified": self.email_verified,
            # Settings UI: whether a local password is set (Google-only accounts
            # have none) and when the account was created.
            "hasPassword": bool(self.password_hash),
            "isGoogle": bool(self.google_sub),
            "createdAt": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class Extraction(db.Model):
    __tablename__ = "extractions"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False, index=True)

    # invoice | receipt
    doc_type = db.Column(db.String(20), nullable=False, default="invoice")

    # File metadata
    file_name = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(100), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)

    # Denormalized headline fields for fast list rendering
    vendor_name = db.Column(db.String(255), nullable=True)
    invoice_number = db.Column(db.String(120), nullable=True)
    invoice_date = db.Column(db.String(40), nullable=True)
    due_date = db.Column(db.String(40), nullable=True)
    currency = db.Column(db.String(10), nullable=True)
    total = db.Column(db.Float, nullable=True)

    # Full structured payload (the invoice JSON) stored as text
    data = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(20), nullable=False, default="completed")  # completed|failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    # Soft delete: a deleted extraction is hidden from History and its uploaded
    # files are removed, but the row is kept so it still counts toward monthly
    # usage (deleting history must not reset a plan/statement quota).
    deleted_at = db.Column(db.DateTime, nullable=True, index=True)

    def list_item(self) -> dict:
        return {
            "id": self.id,
            "docType": self.doc_type,
            "fileName": self.file_name,
            "fileType": self.file_type,
            "vendorName": self.vendor_name,
            "invoiceNumber": self.invoice_number,
            "invoiceDate": self.invoice_date,
            "currency": self.currency,
            "total": self.total,
            "status": self.status,
            "createdAt": self.created_at.isoformat() + "Z",
        }


class ApiKey(db.Model):
    __tablename__ = "api_keys"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, default="API key")
    prefix = db.Column(db.String(20), nullable=False)   # shown in UI, e.g. ip_live_a1b2
    key_hash = db.Column(db.String(255), nullable=False, index=True)  # sha256 of full key
    last_used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "prefix": self.prefix,
            "lastUsedAt": self.last_used_at.isoformat() + "Z" if self.last_used_at else None,
            "createdAt": self.created_at.isoformat() + "Z",
        }


class Webhook(db.Model):
    __tablename__ = "webhooks"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False, index=True)
    url = db.Column(db.String(2048), nullable=False)
    secret = db.Column(db.String(80), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    last_status = db.Column(db.Integer, nullable=True)   # HTTP status of last delivery
    last_delivery_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def public(self, include_secret: bool = False) -> dict:
        data = {
            "id": self.id,
            "url": self.url,
            "active": self.active,
            "lastStatus": self.last_status,
            "lastDeliveryAt": self.last_delivery_at.isoformat() + "Z" if self.last_delivery_at else None,
            "createdAt": self.created_at.isoformat() + "Z",
        }
        if include_secret:
            data["secret"] = self.secret
        return data
