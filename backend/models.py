"""SQLAlchemy models: User and Extraction."""
import uuid
from datetime import datetime

from extensions import db
from money import as_json


def _uuid() -> str:
    return uuid.uuid4().hex


class Organization(db.Model):
    """A tenant. Everything a business owns hangs off one of these.

    Every user gets a personal organization on sign-up, so a single-person
    account is just an organization of one and the app behaves exactly as it did
    before tenancy existed. Teams are the same structure with more members.

    The PLAN lives here, not on the user. A team shares one allowance: if the
    plan sat on the user, five colleagues on one subscription would each get
    their own monthly quota, and "number of users" could not be a pricing
    dimension at all.
    """
    __tablename__ = "organizations"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    name = db.Column(db.String(200), nullable=False)
    # Set for the organization created automatically with an account. Used to
    # pick a sensible default when a user belongs to several, and to stop
    # someone deleting the org that holds their own data.
    is_personal = db.Column(db.Boolean, nullable=False, default=False)

    plan = db.Column(db.String(20), nullable=False, default="free")  # free|starter|pro|business

    # Organization profile, collected during onboarding (Phase 1.8).
    country = db.Column(db.String(2), nullable=True)       # ISO 3166-1 alpha-2
    tax_id = db.Column(db.String(60), nullable=True)
    # Default currency for reports. Individual documents keep their own.
    currency = db.Column(db.String(3), nullable=True)      # ISO 4217

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    memberships = db.relationship(
        "OrganizationMembership", backref="organization",
        cascade="all, delete-orphan", lazy="dynamic",
    )

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "isPersonal": self.is_personal,
            "plan": self.plan,
            "country": self.country,
            "taxId": self.tax_id,
            "currency": self.currency,
            "createdAt": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class OrganizationMembership(db.Model):
    """Which user belongs to which organization, and in what role.

    The role is on the membership rather than the user, so the same person can
    own their own organization and be a read-only viewer in a client's.
    """
    __tablename__ = "organization_memberships"
    __table_args__ = (
        # One membership per user per organization. This is also what makes a
        # duplicate invite harmless rather than a second, conflicting role.
        db.UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
    )

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False, index=True)
    role = db.Column(db.String(40), nullable=False, default="accountant")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def public(self) -> dict:
        return {
            "id": self.id,
            "organizationId": self.organization_id,
            "userId": self.user_id,
            "role": self.role,
            "createdAt": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=True)
    # Null for accounts created via Google (no local password).
    password_hash = db.Column(db.String(255), nullable=True)
    google_sub = db.Column(db.String(64), unique=True, nullable=True, index=True)
    image = db.Column(db.String(1024), nullable=True)
    # NOTE: the plan lives on Organization, not here. A team shares one monthly
    # allowance, so a per-user plan would hand every colleague their own quota.
    # Resolve it with tenancy.current_organization().plan.
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
    payments = db.relationship(
        "Payment", backref="user", cascade="all, delete-orphan", lazy="dynamic"
    )
    subscriptions = db.relationship(
        "Subscription", backref="user", cascade="all, delete-orphan", lazy="dynamic"
    )
    memberships = db.relationship(
        "OrganizationMembership", backref="user", cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def public(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
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
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    # Who uploaded it. Kept alongside organization_id for the audit trail:
    # the organization owns the document, a person created it.
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
    # Numeric, never Float: binary floating point cannot represent most
    # decimal fractions, so a Float column silently disagrees with the figure
    # printed on the document. 4 places leaves headroom for currencies with
    # more than 2 minor units. See money.py.
    total = db.Column(db.Numeric(18, 4), nullable=True)

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


class DemoUsage(db.Model):
    """Durable per-IP counter for the try-before-signup demo.

    Kept separate from DemoExtraction (which is purged after a day) so that
    purging stored results never hands an IP a fresh free extraction. The IP is
    stored only as a salted hash — we never need the address itself.
    """
    __tablename__ = "demo_usage"

    ip_hash = db.Column(db.String(64), primary_key=True)
    count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_at = db.Column(db.DateTime, default=datetime.utcnow)


class DemoExtraction(db.Model):
    """An extraction run by an anonymous visitor on the landing page.

    Holds the result (and the uploaded file) just long enough for the visitor to
    create an account and claim it, so signing up doesn't mean re-uploading. Rows
    older than Config.DEMO_RETENTION_HOURS are purged, claimed or not.
    """
    __tablename__ = "demo_extractions"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    ip_hash = db.Column(db.String(64), nullable=False, index=True)
    # Single-use secret the browser holds and presents to claim this result.
    claim_token = db.Column(db.String(64), nullable=False, unique=True, index=True)

    doc_type = db.Column(db.String(20), nullable=False, default="invoice")
    file_name = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(100), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    data = db.Column(db.Text, nullable=False)

    claimed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class ApiKey(db.Model):
    __tablename__ = "api_keys"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
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


class Payment(db.Model):
    """A payment/subscription event received from the payment provider.

    Recorded by the billing webhook so the user can see a history of charges and
    confirm a payment landed — independent of whether it triggered a plan change.
    """
    __tablename__ = "payments"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False, index=True)
    # Plan this payment was for (from checkout metadata), when known.
    plan = db.Column(db.String(20), nullable=True)
    # Amount in MAJOR units (49.00 means forty-nine), as an exact Decimal.
    #
    # This was an integer of minor units when the provider was Paystack, which
    # reports kobo/cents. Bachs reports decimal strings in major units, and
    # storing minor units meant converting somewhere - which, done backwards,
    # turns $49.00 into $0.49. Major units are the storage contract now, and the
    # provider converts at its own boundary if it needs to.
    amount = db.Column(db.Numeric(18, 4), nullable=True)
    currency = db.Column(db.String(10), nullable=True)
    # The provider's status string (e.g. "succeeded") and the event that produced it.
    status = db.Column(db.String(40), nullable=True)
    event_type = db.Column(db.String(60), nullable=True)
    # Provider identifiers (charge/invoice id, subscription id), for
    # cross-referencing in their dashboard.
    provider_payment_id = db.Column(db.String(120), nullable=True, index=True)
    provider_subscription_id = db.Column(db.String(120), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def public(self) -> dict:
        return {
            "id": self.id,
            "plan": self.plan,
            # Already major units; as_json only quantizes and stringifies.
            "amount": as_json(self.amount),
            "currency": self.currency,
            "status": self.status,
            "eventType": self.event_type,
            "paymentId": self.provider_payment_id,
            "createdAt": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class Subscription(db.Model):
    """Link between one of our users and a provider-side subscription.

    Needed because a renewal invoice does not reliably carry our metadata.
    Bachs documents checkout metadata as copied onto the *subscription*, but says
    nothing about propagation to invoices - and the renewal invoice is exactly
    the event that must extend a paying customer's access. So the provider's
    subscription id is recorded the first time it is seen (from a checkout or a
    subscription.created event, both of which do carry metadata), and later
    events are matched on that id instead of on metadata that may be absent.

    Also the only place that knows a subscription exists at all, which is what
    lets the account page offer a cancel action and lets a missed webhook be
    reconciled later.
    """
    __tablename__ = "subscriptions"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False, index=True)
    provider = db.Column(db.String(20), nullable=False, default="bachs")
    # Provider's subscription id (sub_...). Unique: one row per subscription, so
    # an at-least-once webhook cannot create duplicates.
    provider_subscription_id = db.Column(db.String(120), nullable=False, unique=True, index=True)
    # Provider's customer id (cust_...), for correlating events that identify the
    # customer but not the subscription.
    provider_customer_id = db.Column(db.String(120), nullable=True, index=True)
    # The plan this subscription entitles, and the provider's own status string
    # (trialing | active | past_due | unpaid | canceled | paused).
    plan = db.Column(db.String(20), nullable=True)
    status = db.Column(db.String(40), nullable=True)
    # True once a cancellation is scheduled. Access continues to period end, so
    # this is NOT the same as having lost access.
    cancel_at_period_end = db.Column(db.Boolean, nullable=False, default=False)
    current_period_end = db.Column(db.DateTime, nullable=True)
    # created_at of the newest provider event applied to this row. Deliveries
    # can arrive out of order, and the docs say to compare timestamps before
    # overwriting state: without this, a delayed "subscription.deleted" landing
    # after a fresh "subscription.created" would revoke a paying customer.
    last_event_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def public(self) -> dict:
        return {
            "id": self.id,
            "provider": self.provider,
            "subscriptionId": self.provider_subscription_id,
            "plan": self.plan,
            "status": self.status,
            "cancelAtPeriodEnd": self.cancel_at_period_end,
            "currentPeriodEnd": (
                self.current_period_end.isoformat() + "Z" if self.current_period_end else None
            ),
        }


class ProviderEvent(db.Model):
    """Record of a provider webhook event we have already applied.

    Delivery is at-least-once: Bachs retries on timeouts and 5xx, so the same
    event can legitimately arrive several times. Most of the handling is
    idempotent anyway (setting a plan, upserting a payment keyed on its id), but
    recording the envelope id makes that guarantee explicit instead of
    incidental, and keeps a duplicate from re-sending a "your plan changed"
    email or re-running side effects added later.

    The unique constraint is the mechanism: a concurrent duplicate loses the
    insert race and is skipped rather than processed twice.
    """
    __tablename__ = "provider_events"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    provider = db.Column(db.String(20), nullable=False, default="bachs")
    # The provider's own event id (evt_...).
    event_id = db.Column(db.String(120), nullable=False, unique=True, index=True)
    event_type = db.Column(db.String(60), nullable=True)
    received_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Webhook(db.Model):
    __tablename__ = "webhooks"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
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
