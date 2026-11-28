"""SQLAlchemy models."""
import uuid
from datetime import datetime
from decimal import Decimal

from extensions import db
from money import as_json


def _uuid() -> str:
    return uuid.uuid4().hex


def _iso(value) -> str | None:
    """A datetime as an ISO-8601 UTC string, or None.

    In one place so every model renders timestamps identically; the clients
    parse these, and two formats in one payload is a bug waiting to happen.
    """
    return value.isoformat() + "Z" if value else None


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

    # Set when the owner dismisses the setup checklist. The checklist itself is
    # derived from real state (is the email verified, are there documents yet),
    # never from "I clicked next" - a stored wizard position lies the moment
    # anything changes underneath it. This column only records "stop showing me
    # this", which is genuinely a preference and cannot be derived.
    onboarding_dismissed_at = db.Column(db.DateTime, nullable=True)

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
            "onboardingDismissed": self.onboarding_dismissed_at is not None,
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
        "Extraction",
        # Extraction now has TWO foreign keys to users - the uploader and the
        # reviewer - so the join has to be named explicitly. This relationship
        # means "documents this person uploaded".
        foreign_keys="Extraction.user_id",
        backref="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
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
    # The supplier this document is attributed to, matched on upload or set by
    # hand. Nullable: an unreadable supplier name must not block the upload.
    supplier_id = db.Column(
        db.String, db.ForeignKey("suppliers.id"), nullable=True, index=True
    )
    # SHA-256 over the uploaded bytes. The cheapest and most certain duplicate
    # signal there is: identical bytes are the same document, whatever the
    # extractor made of them. Nullable because rows created before this existed
    # have none, and back-filling would mean re-reading every stored file.
    file_hash = db.Column(db.String(64), nullable=True, index=True)

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

    # ── Processing record ───────────────────────────────────────────────────
    # Denormalized so the history list can FILTER and SORT in SQL. Validation
    # itself is still recomputed from the document on read (so it stays correct
    # after an edit); this column is the *last known* verdict, kept in step
    # whenever the document is written.
    validation_status = db.Column(db.String(30), nullable=True, index=True)
    validation_issue_count = db.Column(db.Integer, nullable=False, default=0)
    # How many fields the extractor actually filled, for "was this a good read?"
    extracted_field_count = db.Column(db.Integer, nullable=False, default=0)
    # Wall-clock milliseconds spent in extraction. Surfaces a slow model or a
    # pathological document without digging through logs.
    processing_ms = db.Column(db.Integer, nullable=True)
    # Why a failed extraction failed, in words, so History can show it without
    # the client parsing the stored payload.
    error_message = db.Column(db.String(500), nullable=True)
    # ── Payment position (P2.6) ─────────────────────────────────────────
    # A cache with a single writer (payments.recompute_payment_state), in the
    # same spirit as validation_status: the figures are always recomputed from
    # the payment rows, and these columns exist so "show me everything
    # overdue" is a question SQL can answer without loading every invoice.
    amount_paid = db.Column(db.Numeric(18, 4), nullable=False, default=0)
    # unpaid | partially_paid | paid | overdue | disputed
    payment_state = db.Column(db.String(20), nullable=True, index=True)
    # A dispute is a human assertion, not a derived figure, so it is stored
    # rather than computed - and it outranks every other state, because an
    # invoice somebody is arguing about must not sit quietly in "overdue".
    disputed_at = db.Column(db.DateTime, nullable=True)
    disputed_by_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)
    dispute_reason = db.Column(db.String(500), nullable=True)

    # ── Background job (F4) ─────────────────────────────────────────────
    # Which queued job owns this row, and when it was handed over. The row is
    # the truth about an extraction, not the job registry — Redis is ephemeral
    # and a job can vanish, which is exactly why `job_queued_at` exists: past
    # a known cutoff the sweeper can state with confidence that nothing is
    # coming back, and fail the row rather than leave it claiming to be busy.
    job_id = db.Column(db.String(120), nullable=True, index=True)
    job_queued_at = db.Column(db.DateTime, nullable=True, index=True)
    job_attempts = db.Column(db.Integer, nullable=False, default=0)

    # Review state: set when a human has looked at and accepted the document.
    reviewed_at = db.Column(db.DateTime, nullable=True, index=True)
    reviewed_by_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    # Soft delete: a deleted extraction is hidden from History and its uploaded
    # files are removed, but the row is kept so it still counts toward monthly
    # usage (deleting history must not reset a plan/statement quota).
    deleted_at = db.Column(db.DateTime, nullable=True, index=True)

    def list_item(self, uploader=None, duplicate_count=0) -> dict:
        """Row shape for the history list.

        Carries enough to triage without opening anything: what it is, whether
        it processed, whether it validates, whether it may be a duplicate, who
        uploaded it and how long it took.
        """
        return {
            "id": self.id,
            "docType": self.doc_type,
            "fileName": self.file_name,
            "fileType": self.file_type,
            "vendorName": self.vendor_name,
            "invoiceNumber": self.invoice_number,
            "invoiceDate": self.invoice_date,
            "currency": self.currency,
            "total": as_json(self.total),
            "status": self.status,
            "createdAt": self.created_at.isoformat() + "Z",
            # Processing record
            "validationStatus": self.validation_status,
            "issueCount": self.validation_issue_count or 0,
            "fieldCount": self.extracted_field_count or 0,
            "processingMs": self.processing_ms,
            "attempts": self.job_attempts or 0,
            "errorMessage": self.error_message,
            "duplicateCount": duplicate_count,
            "amountPaid": as_json(self.amount_paid),
            "paymentState": self.payment_state,
            "dueDate": self.due_date,
            "reviewed": self.reviewed_at is not None,
            "reviewedAt": (
                self.reviewed_at.isoformat() + "Z" if self.reviewed_at else None
            ),
            "uploadedBy": uploader,
        }


class DuplicateMatch(db.Model):
    """A suspected duplicate between two extractions in the same organization.

    Recorded rather than recomputed so a human decision sticks: once someone
    says "these are two genuine invoices that happen to match", that answer
    must survive the next upload and the next page load.

    Deliberately never deletes or rejects anything. Paying an invoice twice is
    expensive, but refusing a legitimate one automatically is worse - a supplier
    really can send two invoices on the same day for the same amount.
    """
    __tablename__ = "duplicate_matches"
    __table_args__ = (
        # One verdict per pair per reason, so re-running detection cannot pile
        # up copies of the same finding.
        db.UniqueConstraint(
            "extraction_id", "duplicate_of_id", "reason",
            name="uq_duplicate_pair_reason",
        ),
    )

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    # The newly uploaded document...
    extraction_id = db.Column(
        db.String, db.ForeignKey("extractions.id"), nullable=False, index=True
    )
    # ...and the earlier one it resembles.
    duplicate_of_id = db.Column(
        db.String, db.ForeignKey("extractions.id"), nullable=False, index=True
    )

    # Which rule fired (see duplicates.py), and how strong it is, 0..1.
    reason = db.Column(db.String(40), nullable=False)
    score = db.Column(db.Float, nullable=False, default=1.0)
    # Human-readable explanation, built when the match is found so the UI does
    # not have to reconstruct the reasoning later.
    detail = db.Column(db.String(500), nullable=True)

    # pending | confirmed (it IS a duplicate) | dismissed (it is not)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    resolved_by_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def public(self, other=None) -> dict:
        data = {
            "id": self.id,
            "extractionId": self.extraction_id,
            "duplicateOfId": self.duplicate_of_id,
            "reason": self.reason,
            "score": self.score,
            "detail": self.detail,
            "status": self.status,
            "createdAt": self.created_at.isoformat() + "Z" if self.created_at else None,
        }
        if other is not None:
            # The document being pointed at, so the reviewer can compare without
            # a second request.
            data["match"] = {
                "id": other.id,
                "fileName": other.file_name,
                "vendorName": other.vendor_name,
                "invoiceNumber": other.invoice_number,
                "invoiceDate": other.invoice_date,
                "total": str(other.total) if other.total is not None else None,
                "currency": other.currency,
                "status": other.status,
                "createdAt": (
                    other.created_at.isoformat() + "Z" if other.created_at else None
                ),
            }
        return data


class FieldCorrection(db.Model):
    """One field a person changed on an extracted document.

    The audit trail the brief asks for, and the reason it matters beyond
    compliance: these rows are the only honest record of where the extractor
    gets things wrong. Aggregated later they say "supplier tax ID is corrected
    40% of the time", which is how the prompt gets improved - a judgement no
    amount of reading the model output can give you.

    The ORIGINAL value is kept forever. Correcting a figure must never destroy
    the evidence of what the document said before someone touched it.
    """
    __tablename__ = "field_corrections"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    extraction_id = db.Column(
        db.String, db.ForeignKey("extractions.id"), nullable=False, index=True
    )
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)

    # Dotted path into the document, e.g. "total" or "line_items.2.unit_price".
    field_path = db.Column(db.String(120), nullable=False, index=True)
    # Stored as text: a field may hold a number, a string or null, and the
    # point is to record exactly what was shown and what replaced it.
    old_value = db.Column(db.String(500), nullable=True)
    new_value = db.Column(db.String(500), nullable=True)
    # Optional free text from the person making the change.
    reason = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def public(self, user_label=None) -> dict:
        return {
            "id": self.id,
            "field": self.field_path,
            "from": self.old_value,
            "to": self.new_value,
            "reason": self.reason,
            "by": user_label,
            "at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class Supplier(db.Model):
    """A business the organization buys from.

    Created manually or adopted automatically from an extracted invoice. Once a
    supplier exists, every invoice bearing its name is attached to it, which is
    what makes "how much do we owe Acme" and later PO matching possible at all.

    Bank details live here and are the highest-value target in the dataset:
    invoice-redirection fraud works by changing them. They are returned only to
    roles holding suppliers:bank:read, and changes to them are worth alerting
    on (P4.4).
    """
    __tablename__ = "suppliers"
    __table_args__ = (
        # Two suppliers in one organization may not share a normalized name.
        # The normalized form is what matching uses, so allowing duplicates
        # would make "which supplier is this invoice from" ambiguous.
        db.UniqueConstraint("organization_id", "match_key", name="uq_supplier_org_key"),
    )

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )

    name = db.Column(db.String(200), nullable=False)
    # Normalized name (lower case, punctuation and company suffixes removed).
    # Stored rather than computed per query so matching is an indexed lookup.
    match_key = db.Column(db.String(200), nullable=False, index=True)

    contact_name = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(254), nullable=True)
    phone = db.Column(db.String(60), nullable=True)
    address = db.Column(db.String(500), nullable=True)
    country = db.Column(db.String(2), nullable=True)        # ISO 3166-1 alpha-2
    tax_id = db.Column(db.String(60), nullable=True, index=True)
    registration_number = db.Column(db.String(60), nullable=True)

    # Commercial defaults, used later by PO matching and payment due dates.
    payment_terms = db.Column(db.String(120), nullable=True)
    currency = db.Column(db.String(3), nullable=True)       # ISO 4217
    notes = db.Column(db.Text, nullable=True)

    # active | archived. Archived rather than deleted: a supplier with invoices
    # against it cannot be removed without orphaning financial history.
    status = db.Column(db.String(20), nullable=False, default="active", index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def public(self, *, include_bank=False, stats=None) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "contactName": self.contact_name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "country": self.country,
            "taxId": self.tax_id,
            "registrationNumber": self.registration_number,
            "paymentTerms": self.payment_terms,
            "currency": self.currency,
            "notes": self.notes,
            "status": self.status,
            "createdAt": self.created_at.isoformat() + "Z" if self.created_at else None,
        }
        if include_bank:
            # Omitted entirely rather than nulled for unauthorized callers: a
            # key that is present-but-empty still tells them it exists.
            data["bankDetails"] = {
                "bankName": self.bank_name,
                "accountName": self.bank_account_name,
                "accountNumber": self.bank_account_number,
                "iban": self.bank_iban,
                "swift": self.bank_swift,
                "sortCode": self.bank_sort_code,
            }
        if stats is not None:
            data["stats"] = stats
        return data

    # Bank details, separated above by permission.
    bank_name = db.Column(db.String(120), nullable=True)
    bank_account_name = db.Column(db.String(200), nullable=True)
    bank_account_number = db.Column(db.String(60), nullable=True)
    bank_iban = db.Column(db.String(60), nullable=True)
    bank_swift = db.Column(db.String(20), nullable=True)
    bank_sort_code = db.Column(db.String(20), nullable=True)


class PurchaseOrder(db.Model):
    """A commitment to buy: what was ordered, from whom, at what price.

    The PO is the control document of accounts payable. An invoice on its own
    proves only that someone sent a demand for money; a PO proves the
    organization agreed to owe it, and at what price. Everything in P2.3 and
    P2.4 (invoice matching, three-way matching) compares an incoming invoice
    against these rows, which drives two design rules:

    1. **Totals are computed, never accepted.** `subtotal`, `tax_total` and
       `total` are derived from the line rows on every write. A client-supplied
       total that disagrees with its own lines is exactly where both bugs and
       fraud hide, and it would silently poison matching.
    2. **An approved PO is immutable.** Approval is approval of specific
       amounts, so commercial terms can only be edited while the PO is a
       draft. To change an approved order you cancel it and raise another,
       which is also how procurement works on paper.
    """
    __tablename__ = "purchase_orders"
    __table_args__ = (
        # One PO number per organization. The number is what suppliers quote
        # back and what invoices reference, so a duplicate would make
        # "which order is this invoice against?" unanswerable.
        db.UniqueConstraint("organization_id", "po_number", name="uq_po_org_number"),
    )

    # Status lifecycle. Declared as data so the allowed transitions live in one
    # readable place rather than scattered across route handlers.
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    PARTIALLY_RECEIVED = "partially_received"
    FULLY_RECEIVED = "fully_received"
    CLOSED = "closed"
    CANCELLED = "cancelled"

    STATUSES = (
        DRAFT, PENDING_APPROVAL, APPROVED, SENT,
        PARTIALLY_RECEIVED, FULLY_RECEIVED, CLOSED, CANCELLED,
    )

    # What may follow what. Anything not listed is rejected, so an unexpected
    # client cannot park a PO in a state the rest of the system cannot read.
    TRANSITIONS: dict[str, set[str]] = {
        DRAFT: {PENDING_APPROVAL, CANCELLED},
        # A rejected PO returns to draft to be corrected and resubmitted.
        PENDING_APPROVAL: {APPROVED, DRAFT, CANCELLED},
        # PARTIALLY_RECEIVED and FULLY_RECEIVED are reachable directly:
        # goods arriving is proof the order reached the supplier, and refusing
        # to record a delivery because nobody pressed "sent" would make the
        # paperwork argue with the loading dock.
        APPROVED: {SENT, PARTIALLY_RECEIVED, FULLY_RECEIVED, CANCELLED},
        SENT: {PARTIALLY_RECEIVED, FULLY_RECEIVED, CANCELLED},
        PARTIALLY_RECEIVED: {FULLY_RECEIVED, CLOSED, CANCELLED},
        FULLY_RECEIVED: {CLOSED},
        # Terminal. A closed order is history; a cancelled one never happened.
        CLOSED: set(),
        CANCELLED: set(),
    }

    # States in which commercial terms may still be edited. Deliberately just
    # the one: see rule 2 above.
    EDITABLE_STATUSES = {DRAFT}

    # States where the order still represents money the organization expects to
    # spend. Used for the open-commitment figure.
    OPEN_STATUSES = {APPROVED, SENT, PARTIALLY_RECEIVED}

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    # Required: you cannot order from nobody, and a PO with no supplier can
    # never be matched, sent or received.
    supplier_id = db.Column(
        db.String, db.ForeignKey("suppliers.id"), nullable=False, index=True
    )
    created_by_user_id = db.Column(
        db.String, db.ForeignKey("users.id"), nullable=False, index=True
    )

    po_number = db.Column(db.String(60), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default=DRAFT, index=True)

    currency = db.Column(db.String(3), nullable=False, default="USD")

    # Derived from the lines on every write. Stored so the list view can sort
    # and filter on value in SQL instead of loading every line.
    subtotal = db.Column(db.Numeric(18, 4), nullable=False, default=0)
    tax_total = db.Column(db.Numeric(18, 4), nullable=False, default=0)
    total = db.Column(db.Numeric(18, 4), nullable=False, default=0)

    # Dates are stored as text in the same ISO form the extractor produces for
    # invoices, so PO and invoice dates compare without a parsing layer that
    # could disagree between the two.
    order_date = db.Column(db.String(40), nullable=True)
    expected_delivery_date = db.Column(db.String(40), nullable=True, index=True)

    payment_terms = db.Column(db.String(120), nullable=True)
    delivery_address = db.Column(db.String(500), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    # The organization's own reference, e.g. a requisition number.
    reference = db.Column(db.String(120), nullable=True, index=True)

    # Cost attribution. Carried now because P2.5 routes approvals by
    # department, cost centre and project; declaring them here avoids a
    # migration that would have to back-fill live orders later.
    department = db.Column(db.String(120), nullable=True, index=True)
    cost_center = db.Column(db.String(120), nullable=True)
    project = db.Column(db.String(120), nullable=True)
    category = db.Column(db.String(120), nullable=True)

    submitted_at = db.Column(db.DateTime, nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by_user_id = db.Column(
        db.String, db.ForeignKey("users.id"), nullable=True
    )
    # Kept after a rejected PO returns to draft, so the person correcting it
    # can see why it came back.
    rejection_reason = db.Column(db.String(500), nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    receipts = db.relationship(
        "GoodsReceipt",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    lines = db.relationship(
        "PurchaseOrderLine",
        back_populates="purchase_order",
        order_by="PurchaseOrderLine.line_no",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    attachments = db.relationship(
        "PurchaseOrderAttachment",
        back_populates="purchase_order",
        order_by="PurchaseOrderAttachment.created_at",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def can_transition_to(self, status: str) -> bool:
        return status in self.TRANSITIONS.get(self.status, set())

    @property
    def is_editable(self) -> bool:
        return self.status in self.EDITABLE_STATUSES

    def list_item(self, supplier_name=None, line_count=None) -> dict:
        """Row shape for the purchase-order list."""
        return {
            "id": self.id,
            "poNumber": self.po_number,
            "status": self.status,
            "supplierId": self.supplier_id,
            "supplierName": supplier_name,
            "currency": self.currency,
            "total": as_json(self.total),
            "orderDate": self.order_date,
            "expectedDeliveryDate": self.expected_delivery_date,
            "reference": self.reference,
            "department": self.department,
            "lineCount": line_count if line_count is not None else len(self.lines),
            "createdAt": self.created_at.isoformat() + "Z" if self.created_at else None,
        }

    def public(self, *, supplier=None, created_by=None, approved_by=None) -> dict:
        return {
            **self.list_item(
                supplier_name=supplier.get("name") if supplier else None
            ),
            "subtotal": as_json(self.subtotal),
            "taxTotal": as_json(self.tax_total),
            "paymentTerms": self.payment_terms,
            "deliveryAddress": self.delivery_address,
            "notes": self.notes,
            "costCenter": self.cost_center,
            "project": self.project,
            "category": self.category,
            "supplier": supplier,
            "lines": [line.public() for line in self.lines],
            "attachments": [a.public() for a in self.attachments],
            "isEditable": self.is_editable,
            "nextStatuses": sorted(self.TRANSITIONS.get(self.status, set())),
            "createdBy": created_by,
            "approvedBy": approved_by,
            "submittedAt": _iso(self.submitted_at),
            "approvedAt": _iso(self.approved_at),
            "rejectedAt": _iso(self.rejected_at),
            "rejectionReason": self.rejection_reason,
            "sentAt": _iso(self.sent_at),
            "closedAt": _iso(self.closed_at),
            "cancelledAt": _iso(self.cancelled_at),
            "updatedAt": _iso(self.updated_at),
        }


class PurchaseOrderLine(db.Model):
    """One ordered item.

    Separate rows rather than a JSON blob on the order, because P2.3 compares
    invoice lines against these and P2.4 tracks how much of each line has
    actually arrived. Stored as JSON, "how much of line 3 is outstanding?"
    stops being a question SQL can answer.
    """
    __tablename__ = "purchase_order_lines"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    purchase_order_id = db.Column(
        db.String, db.ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    # Denormalized from the parent so tenancy.scoped() works on lines directly
    # and a cross-organization read cannot happen through a line id.
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )

    # Position on the order, 1-based. The supplier's invoice refers to "line 2".
    line_no = db.Column(db.Integer, nullable=False, default=1)

    description = db.Column(db.String(500), nullable=False)
    sku = db.Column(db.String(120), nullable=True, index=True)
    unit = db.Column(db.String(40), nullable=True)          # each, kg, hour...

    # Numeric, not Float, for the same reason money is: 0.1 of a tonne has no
    # exact binary representation. Quantities can be fractional.
    quantity = db.Column(db.Numeric(18, 4), nullable=False, default=0)
    unit_price = db.Column(db.Numeric(18, 4), nullable=False, default=0)
    # Percentage, e.g. 7.5000 for 7.5% VAT. Stored as the rate rather than only
    # the resulting amount so a changed quantity recomputes tax correctly.
    tax_rate = db.Column(db.Numeric(9, 4), nullable=False, default=0)

    # Derived. Rounded per line BEFORE summing, because that is what suppliers
    # print and therefore what P2.3 must compare against; rounding only at the
    # end can disagree with the invoice by a cent and raise a false mismatch.
    line_subtotal = db.Column(db.Numeric(18, 4), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(18, 4), nullable=False, default=0)
    line_total = db.Column(db.Numeric(18, 4), nullable=False, default=0)

    # Filled by P2.4 (goods receipts) and P2.3 (invoice matching). Carried now
    # so the received/invoiced position of a line has one home from the start,
    # and never written by the purchase-order API itself.
    quantity_received = db.Column(db.Numeric(18, 4), nullable=False, default=0)
    # What was received LESS what was damaged or sent back. The figure an
    # invoice is measured against, because you do not owe for goods you
    # refused or that arrived broken. Maintained by
    # goods_receipts.recompute_received as a cache with a single writer.
    quantity_accepted = db.Column(db.Numeric(18, 4), nullable=False, default=0)
    quantity_invoiced = db.Column(db.Numeric(18, 4), nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    purchase_order = db.relationship("PurchaseOrder", back_populates="lines")

    def public(self) -> dict:
        return {
            "id": self.id,
            "lineNo": self.line_no,
            "description": self.description,
            "sku": self.sku,
            "unit": self.unit,
            "quantity": as_json(self.quantity),
            "unitPrice": as_json(self.unit_price),
            "taxRate": as_json(self.tax_rate),
            "lineSubtotal": as_json(self.line_subtotal),
            "taxAmount": as_json(self.tax_amount),
            "lineTotal": as_json(self.line_total),
            "quantityReceived": as_json(self.quantity_received),
            "quantityAccepted": as_json(self.quantity_accepted),
            "quantityInvoiced": as_json(self.quantity_invoiced),
        }


class PurchaseOrderAttachment(db.Model):
    """A file attached to a purchase order: a quote, a spec, a signed copy.

    Attachments stay addable after approval. They are evidence about the order,
    not terms of it, so adding one cannot change what was agreed - which is why
    they are exempt from the immutability rule covering lines and prices.
    """
    __tablename__ = "purchase_order_attachments"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    purchase_order_id = db.Column(
        db.String, db.ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    uploaded_by_user_id = db.Column(
        db.String, db.ForeignKey("users.id"), nullable=True
    )

    file_name = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(100), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    # Name on disk only, never a path from the client. Joined to UPLOAD_DIR on
    # read so a stored value can never escape the upload directory.
    stored_name = db.Column(db.String(255), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    purchase_order = db.relationship("PurchaseOrder", back_populates="attachments")

    def public(self) -> dict:
        return {
            "id": self.id,
            "fileName": self.file_name,
            "fileType": self.file_type,
            "fileSize": self.file_size,
            "createdAt": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class MatchingSettings(db.Model):
    """Per-organization tolerances for invoice-to-PO matching.

    One row per organization, created on first read with the defaults below.
    These have to be configurable because the right answer is a commercial
    decision, not a technical one: a builders' merchant delivering steel by
    weight expects quantities to drift, a software reseller does not.

    Every tolerance is expressed BOTH as a percentage and as an absolute
    amount, and a difference passes if it is within EITHER. A percentage alone
    is useless at both ends of the scale - 1% of a 50.00 line is 0.50, which
    flags ordinary rounding as a discrepancy, while 1% of 5,000,000.00 is
    50,000.00, which waves a real error through.
    """
    __tablename__ = "matching_settings"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"),
        nullable=False, unique=True, index=True,
    )

    # Unit price. The default allows two kobo/cents of rounding and nothing
    # more, because a unit price is quoted, agreed and written down - unlike a
    # quantity, it has no physical reason to vary.
    price_tolerance_percent = db.Column(db.Numeric(9, 4), nullable=False, default=0)
    price_tolerance_amount = db.Column(
        db.Numeric(18, 4), nullable=False, default=Decimal("0.02")
    )

    # Quantity. Defaults to exact: shipping more than was ordered is a
    # commercial event someone should see, not noise to absorb.
    quantity_tolerance_percent = db.Column(db.Numeric(9, 4), nullable=False, default=0)
    quantity_tolerance_amount = db.Column(db.Numeric(18, 4), nullable=False, default=0)

    # Invoice total against the order's remaining value.
    total_tolerance_percent = db.Column(db.Numeric(9, 4), nullable=False, default=0)
    total_tolerance_amount = db.Column(
        db.Numeric(18, 4), nullable=False, default=Decimal("0.02")
    )

    # An invoice that cites no purchase order at all. Off by default because
    # plenty of legitimate spend - utilities, rent, a taxi - never has one.
    # Organizations running strict three-way matching turn it on.
    require_po_reference = db.Column(db.Boolean, nullable=False, default=False)

    # Invoicing against an order nobody approved. On by default: this is the
    # control that stops spend being committed after the fact.
    block_unapproved_po = db.Column(db.Boolean, nullable=False, default=True)

    # Block an invoice for goods that were never recorded as received, and
    # for quantities beyond what was accepted. On by default - billing for
    # undelivered goods is the classic payables loss - but it only fires for
    # an organization that has actually posted a goods receipt, so turning the
    # feature on is what switches the control on. Without that condition,
    # every invoice in every organization not using receipts would block the
    # day this shipped.
    require_goods_receipt = db.Column(db.Boolean, nullable=False, default=True)

    # Link an invoice to its order automatically when the PO number on the
    # document is an exact hit AND the comparison comes back clean. This
    # confirms the LINK, never the invoice: approval is P2.5's decision and is
    # gated separately. With this off, every link waits for a person.
    auto_confirm_exact = db.Column(db.Boolean, nullable=False, default=True)

    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    updated_by_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)

    def public(self) -> dict:
        return {
            "priceTolerancePercent": as_json(self.price_tolerance_percent),
            "priceToleranceAmount": as_json(self.price_tolerance_amount),
            "quantityTolerancePercent": as_json(self.quantity_tolerance_percent),
            "quantityToleranceAmount": as_json(self.quantity_tolerance_amount),
            "totalTolerancePercent": as_json(self.total_tolerance_percent),
            "totalToleranceAmount": as_json(self.total_tolerance_amount),
            "requirePoReference": bool(self.require_po_reference),
            "blockUnapprovedPo": bool(self.block_unapproved_po),
            "requireGoodsReceipt": bool(self.require_goods_receipt),
            "autoConfirmExact": bool(self.auto_confirm_exact),
            "updatedAt": _iso(self.updated_at),
        }


class InvoiceMatch(db.Model):
    """The link between one extracted invoice and the purchase order it bills.

    At most one per invoice, enforced by a unique constraint: "which order does
    this invoice belong to?" must have exactly one answer, or the amount
    invoiced against an order is not a number anyone can compute.

    Two fields look similar and mean different things:

    * `status` is what a PERSON has decided about the link - suggested,
      confirmed, or rejected. It persists.
    * `outcome` is what the COMPARISON found - matched, discrepancy, or failed.
      It is recomputed from the live document and order on every read (so it
      stays correct after someone corrects an extracted figure) and this column
      is only the last known verdict, kept for filtering and sorting in SQL.
      The same arrangement as `Extraction.validation_status`.

    An override is recorded here rather than making the findings disappear. A
    discrepancy that a human accepted is still a discrepancy; what changed is
    that someone took responsibility for it, and their name and reason are the
    useful part of that record.
    """
    __tablename__ = "invoice_matches"
    __table_args__ = (
        db.UniqueConstraint("extraction_id", name="uq_invoice_match_extraction"),
    )

    # Who decided, and what they decided about the link.
    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    STATUSES = (SUGGESTED, CONFIRMED, REJECTED)

    # What the comparison found, best first.
    MATCHED = "matched"
    DISCREPANCY = "discrepancy"
    FAILED = "failed"
    OUTCOMES = (MATCHED, DISCREPANCY, FAILED)

    # How the order was found. Recorded because a wrong link is much easier to
    # explain afterwards when you know which signal produced it.
    BY_PO_NUMBER = "po_number"
    BY_PO_REFERENCE = "po_reference"
    BY_SUPPLIER_AMOUNT = "supplier_amount"
    BY_MANUAL = "manual"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    extraction_id = db.Column(
        db.String, db.ForeignKey("extractions.id"), nullable=False, index=True
    )
    purchase_order_id = db.Column(
        db.String, db.ForeignKey("purchase_orders.id"), nullable=False, index=True
    )

    status = db.Column(db.String(20), nullable=False, default=SUGGESTED, index=True)
    method = db.Column(db.String(30), nullable=False, default=BY_MANUAL)
    # 0..1, how much evidence the link itself rests on - not how well the
    # figures agreed, which is `outcome`.
    score = db.Column(db.Float, nullable=False, default=0.0)

    outcome = db.Column(db.String(20), nullable=True, index=True)
    blocking_count = db.Column(db.Integer, nullable=False, default=0)
    review_count = db.Column(db.Integer, nullable=False, default=0)

    confirmed_by_user_id = db.Column(
        db.String, db.ForeignKey("users.id"), nullable=True
    )
    confirmed_at = db.Column(db.DateTime, nullable=True)

    # An accepted discrepancy. The note is mandatory at the API edge: "approved
    # anyway" with no reason is not an audit trail.
    override_note = db.Column(db.String(500), nullable=True)
    overridden_by_user_id = db.Column(
        db.String, db.ForeignKey("users.id"), nullable=True
    )
    overridden_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    created_by_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)

    @property
    def is_overridden(self) -> bool:
        return self.overridden_at is not None

    def public(self, *, purchase_order=None, extraction=None, comparison=None,
               confirmed_by=None, overridden_by=None) -> dict:
        """The match, optionally with the live comparison and both documents.

        `comparison` is passed in rather than computed here: a model should not
        reach back into the matching engine, and the caller already has the
        order and the parsed document the comparison needs.
        """
        data = {
            "id": self.id,
            "extractionId": self.extraction_id,
            "purchaseOrderId": self.purchase_order_id,
            "status": self.status,
            "method": self.method,
            "score": self.score,
            "outcome": self.outcome,
            "blockingCount": self.blocking_count or 0,
            "reviewCount": self.review_count or 0,
            "overridden": self.is_overridden,
            "overrideNote": self.override_note,
            "overriddenBy": overridden_by,
            "overriddenAt": _iso(self.overridden_at),
            "confirmedBy": confirmed_by,
            "confirmedAt": _iso(self.confirmed_at),
            "createdAt": _iso(self.created_at),
        }
        if purchase_order is not None:
            data["purchaseOrder"] = {
                "id": purchase_order.id,
                "poNumber": purchase_order.po_number,
                "status": purchase_order.status,
                "currency": purchase_order.currency,
                "total": as_json(purchase_order.total),
                "supplierId": purchase_order.supplier_id,
            }
        if extraction is not None:
            data["invoice"] = {
                "id": extraction.id,
                "fileName": extraction.file_name,
                "vendorName": extraction.vendor_name,
                "invoiceNumber": extraction.invoice_number,
                "invoiceDate": extraction.invoice_date,
                "currency": extraction.currency,
                "total": as_json(extraction.total),
                "supplierId": extraction.supplier_id,
            }
        if comparison is not None:
            data["comparison"] = comparison
        return data


class GoodsReceipt(db.Model):
    """What actually turned up, against one purchase order.

    The third leg of three-way matching. An order says what was agreed and an
    invoice says what is being charged; neither is evidence that anything
    arrived, and "we paid for goods we never received" is the oldest loss in
    accounts payable.

    A receipt is a statement of fact rather than a request, so there is no
    approval step. There is a `posted` step: only a posted receipt counts
    toward what has been received, the same rule that stops an unconfirmed
    invoice match consuming an order's value. A half-entered delivery note
    sitting in draft must not make an invoice payable.

    Nothing is ever deleted. A receipt recorded in error is cancelled, because
    it is a record of a physical event somebody asserted at a point in time.
    """
    __tablename__ = "goods_receipts"
    __table_args__ = (
        db.UniqueConstraint("organization_id", "grn_number", name="uq_grn_org_number"),
    )

    DRAFT = "draft"
    POSTED = "posted"
    CANCELLED = "cancelled"
    STATUSES = (DRAFT, POSTED, CANCELLED)

    TRANSITIONS: dict[str, set[str]] = {
        DRAFT: {POSTED, CANCELLED},
        # A posted receipt can still be cancelled - goods get returned, and a
        # delivery note gets mis-keyed - but it cannot quietly go back to
        # draft, because invoices may already have been matched against it.
        POSTED: {CANCELLED},
        CANCELLED: set(),
    }
    EDITABLE_STATUSES = {DRAFT}

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    purchase_order_id = db.Column(
        db.String, db.ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    grn_number = db.Column(db.String(60), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default=DRAFT, index=True)

    # Same text ISO form as the order dates, so the two compare without a
    # parsing layer between them.
    received_date = db.Column(db.String(40), nullable=True)
    # The supplier's own delivery/dispatch note number, which is what a
    # warehouse argument is actually settled with.
    delivery_note_ref = db.Column(db.String(120), nullable=True)
    carrier = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    received_by_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)
    created_by_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)
    posted_at = db.Column(db.DateTime, nullable=True)
    posted_by_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancelled_by_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)
    cancellation_reason = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    lines = db.relationship(
        "GoodsReceiptLine",
        back_populates="goods_receipt",
        cascade="all, delete-orphan",
        order_by="GoodsReceiptLine.line_no",
        lazy="selectin",
    )
    purchase_order = db.relationship("PurchaseOrder", back_populates="receipts")

    def can_transition_to(self, status: str) -> bool:
        return status in self.TRANSITIONS.get(self.status, set())

    @property
    def is_editable(self) -> bool:
        return self.status in self.EDITABLE_STATUSES

    def list_item(self, line_count=None) -> dict:
        return {
            "id": self.id,
            "grnNumber": self.grn_number,
            "status": self.status,
            "purchaseOrderId": self.purchase_order_id,
            "receivedDate": self.received_date,
            "deliveryNoteRef": self.delivery_note_ref,
            "lineCount": line_count if line_count is not None else len(self.lines),
            "createdAt": _iso(self.created_at),
            "postedAt": _iso(self.posted_at),
        }

    def public(self, *, purchase_order=None, received_by=None, posted_by=None) -> dict:
        data = {
            "id": self.id,
            "grnNumber": self.grn_number,
            "status": self.status,
            "isEditable": self.is_editable,
            "nextStatuses": sorted(self.TRANSITIONS.get(self.status, set())),
            "purchaseOrderId": self.purchase_order_id,
            "receivedDate": self.received_date,
            "deliveryNoteRef": self.delivery_note_ref,
            "carrier": self.carrier,
            "notes": self.notes,
            "receivedBy": received_by,
            "postedBy": posted_by,
            "postedAt": _iso(self.posted_at),
            "cancelledAt": _iso(self.cancelled_at),
            "cancellationReason": self.cancellation_reason,
            "createdAt": _iso(self.created_at),
            "lines": [line.public() for line in self.lines],
        }
        if purchase_order is not None:
            data["purchaseOrder"] = {
                "id": purchase_order.id,
                "poNumber": purchase_order.po_number,
                "status": purchase_order.status,
                "currency": purchase_order.currency,
                "supplierId": purchase_order.supplier_id,
            }
        return data


class GoodsReceiptLine(db.Model):
    """One ordered item, as it actually arrived.

    Three counts, because they have three different consequences and lumping
    them together loses the one fact that decides who pays:

    * `quantity_received` - what physically arrived.
    * `quantity_damaged`  - of those, how many arrived broken.
    * `quantity_rejected` - how many were sent back intact: wrong item, wrong
      specification, short-dated stock.

    `quantity_accepted` is what is left, and it is the only one of the four
    that matching uses. You do not owe a supplier for goods you refused or for
    goods that arrived smashed, so an invoice is measured against what was
    accepted - never against what was delivered.
    """
    __tablename__ = "goods_receipt_lines"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    goods_receipt_id = db.Column(
        db.String, db.ForeignKey("goods_receipts.id"), nullable=False, index=True
    )
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    # Always against a specific order line: "we received 8 of something" is not
    # a fact anything can be matched against.
    purchase_order_line_id = db.Column(
        db.String, db.ForeignKey("purchase_order_lines.id"), nullable=False, index=True
    )

    line_no = db.Column(db.Integer, nullable=False, default=1)

    # Numeric, not Float, for the same reason the order lines are: 0.1 of a
    # tonne has no exact binary representation.
    quantity_received = db.Column(db.Numeric(18, 4), nullable=False, default=0)
    quantity_damaged = db.Column(db.Numeric(18, 4), nullable=False, default=0)
    quantity_rejected = db.Column(db.Numeric(18, 4), nullable=False, default=0)
    # Stored rather than derived on read, so the arithmetic is done once, in
    # one place, and a query can sum it without loading every row into Python.
    quantity_accepted = db.Column(db.Numeric(18, 4), nullable=False, default=0)

    # Why some were refused or written off. The useful half of the record when
    # somebody queries the invoice three weeks later.
    notes = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    goods_receipt = db.relationship("GoodsReceipt", back_populates="lines")
    purchase_order_line = db.relationship("PurchaseOrderLine")

    def public(self) -> dict:
        po_line = self.purchase_order_line
        return {
            "id": self.id,
            "lineNo": self.line_no,
            "purchaseOrderLineId": self.purchase_order_line_id,
            "description": po_line.description if po_line else None,
            "sku": po_line.sku if po_line else None,
            "unit": po_line.unit if po_line else None,
            "quantityOrdered": as_json(po_line.quantity) if po_line else None,
            "quantityReceived": as_json(self.quantity_received),
            "quantityDamaged": as_json(self.quantity_damaged),
            "quantityRejected": as_json(self.quantity_rejected),
            "quantityAccepted": as_json(self.quantity_accepted),
            "notes": self.notes,
        }


class ApprovalRule(db.Model):
    """When approval is needed, and from whom. Configuration, not code.

    The brief's requirement is "configurable, not hardcoded", and the reason
    is not flexibility for its own sake: every organization draws the line in
    a different place, and a threshold baked into a deployment is one that
    gets changed by a developer at the worst possible moment.

    Conditions are ANDed, and an unset condition does not constrain. A rule
    with no conditions at all therefore matches everything, which is the
    normal way to express "everything needs one approval".

    **The highest-priority matching rule wins, and only that one applies.**
    Combining every matching rule would produce approval chains nobody can
    predict or explain - and an approval chain you cannot explain is one
    people route around.
    """
    __tablename__ = "approval_rules"

    PURCHASE_ORDER = "purchase_order"
    INVOICE = "invoice"
    SUBJECTS = (PURCHASE_ORDER, INVOICE)

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    name = db.Column(db.String(200), nullable=False)
    subject_type = db.Column(db.String(30), nullable=False, default=PURCHASE_ORDER,
                             index=True)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    # Higher wins. Ties break on creation order, so a rule added later does not
    # silently displace an existing one of equal priority.
    priority = db.Column(db.Integer, nullable=False, default=0)

    # ── Conditions. All optional; all ANDed. ──
    # Numeric, never Float: these are compared against money, and a Float
    # threshold would disagree with the Numeric totals it is gating.
    min_amount = db.Column(db.Numeric(18, 4), nullable=True)
    max_amount = db.Column(db.Numeric(18, 4), nullable=True)
    currency = db.Column(db.String(3), nullable=True)
    department = db.Column(db.String(120), nullable=True)
    cost_center = db.Column(db.String(120), nullable=True)
    project = db.Column(db.String(120), nullable=True)
    category = db.Column(db.String(120), nullable=True)
    supplier_id = db.Column(db.String, db.ForeignKey("suppliers.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    created_by_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    steps = db.relationship(
        "ApprovalRuleStep",
        back_populates="rule",
        cascade="all, delete-orphan",
        order_by="ApprovalRuleStep.level",
        lazy="selectin",
    )

    def public(self, *, supplier_name=None) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "subjectType": self.subject_type,
            "active": bool(self.active),
            "priority": self.priority,
            "conditions": {
                "minAmount": as_json(self.min_amount),
                "maxAmount": as_json(self.max_amount),
                "currency": self.currency,
                "department": self.department,
                "costCenter": self.cost_center,
                "project": self.project,
                "category": self.category,
                "supplierId": self.supplier_id,
                "supplierName": supplier_name,
            },
            "steps": [step.public() for step in self.steps],
            "createdAt": _iso(self.created_at),
        }


class ApprovalRuleStep(db.Model):
    """One level of a rule's approval chain.

    Levels run in order: level 2 is not asked until level 1 is satisfied, so a
    director is not troubled by something their manager is going to reject.
    Approvers *within* a level are asked at the same time - that is what
    "parallel" means here - and `require_all` decides whether every one of
    them must sign or any one is enough.
    """
    __tablename__ = "approval_rule_steps"

    BY_ROLE = "role"
    BY_USER = "user"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    rule_id = db.Column(
        db.String, db.ForeignKey("approval_rules.id"), nullable=False, index=True
    )
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    level = db.Column(db.Integer, nullable=False, default=1)

    # A role rather than a person wherever possible: naming an individual is
    # how an approval chain breaks the week they leave.
    approver_type = db.Column(db.String(20), nullable=False, default=BY_ROLE)
    approver_role = db.Column(db.String(40), nullable=True)
    approver_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)

    require_all = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    rule = db.relationship("ApprovalRule", back_populates="steps")

    def public(self) -> dict:
        return {
            "id": self.id,
            "level": self.level,
            "approverType": self.approver_type,
            "approverRole": self.approver_role,
            "approverUserId": self.approver_user_id,
            "requireAll": bool(self.require_all),
        }


class ApprovalRequest(db.Model):
    """One document's journey through an approval chain.

    The chain is **materialized at submission** into `ApprovalRequestStep`
    rows rather than re-read from the rule on every decision. Editing a rule
    must not rewrite an approval that is already in flight: the people who
    signed it signed a specific chain, and an audit trail that changes shape
    retrospectively is not one.

    `amount` and `currency` are snapshots for the same reason - what was
    approved, not what the document says today.
    """
    __tablename__ = "approval_requests"

    PENDING = "pending"
    INFO_REQUESTED = "info_requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    STATUSES = (PENDING, INFO_REQUESTED, APPROVED, REJECTED, CANCELLED)
    OPEN_STATUSES = (PENDING, INFO_REQUESTED)

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    subject_type = db.Column(db.String(30), nullable=False, index=True)
    subject_id = db.Column(db.String(64), nullable=False, index=True)

    # Which rule produced this chain. Nullable: a request raised when no rule
    # matched still needs somewhere to live.
    rule_id = db.Column(db.String, db.ForeignKey("approval_rules.id"), nullable=True)
    rule_name = db.Column(db.String(200), nullable=True)

    status = db.Column(db.String(20), nullable=False, default=PENDING, index=True)
    current_level = db.Column(db.Integer, nullable=False, default=1)

    amount = db.Column(db.Numeric(18, 4), nullable=True)
    currency = db.Column(db.String(10), nullable=True)

    submitted_by_user_id = db.Column(
        db.String, db.ForeignKey("users.id"), nullable=True
    )
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    # The last decision's words, surfaced without loading the whole history.
    outcome_comment = db.Column(db.String(1000), nullable=True)
    last_reminded_at = db.Column(db.DateTime, nullable=True)

    steps = db.relationship(
        "ApprovalRequestStep",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="ApprovalRequestStep.level",
        lazy="selectin",
    )
    events = db.relationship(
        "ApprovalEvent",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="ApprovalEvent.created_at",
        lazy="selectin",
    )

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES

    def public(self, *, labels=None, subject=None) -> dict:
        labels = labels or {}
        data = {
            "id": self.id,
            "subjectType": self.subject_type,
            "subjectId": self.subject_id,
            "status": self.status,
            "isOpen": self.is_open,
            "currentLevel": self.current_level,
            "ruleId": self.rule_id,
            "ruleName": self.rule_name,
            "amount": as_json(self.amount),
            "currency": self.currency,
            "submittedBy": labels.get(self.submitted_by_user_id),
            "submittedAt": _iso(self.submitted_at),
            "completedAt": _iso(self.completed_at),
            "outcomeComment": self.outcome_comment,
            "lastRemindedAt": _iso(self.last_reminded_at),
            "steps": [step.public(labels=labels) for step in self.steps],
            "history": [event.public(labels=labels) for event in self.events],
        }
        if subject is not None:
            data["subject"] = subject
        return data


class ApprovalRequestStep(db.Model):
    """One person's place in one approval chain.

    A row per approver, not per level, so "who still has not responded" is a
    question SQL can answer and a reminder knows where to go.
    """
    __tablename__ = "approval_request_steps"

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    STATUSES = (PENDING, APPROVED, REJECTED, SKIPPED)

    id = db.Column(db.String, primary_key=True, default=_uuid)
    request_id = db.Column(
        db.String, db.ForeignKey("approval_requests.id"), nullable=False, index=True
    )
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    level = db.Column(db.Integer, nullable=False, default=1)

    # Resolved to a person at materialization where the rule named a role, so
    # the chain is a list of names rather than a puzzle to re-solve later.
    approver_user_id = db.Column(
        db.String, db.ForeignKey("users.id"), nullable=True, index=True
    )
    # Kept alongside, because "the finance manager approved this" is the
    # meaningful statement and the person may hold a different role later.
    approver_role = db.Column(db.String(40), nullable=True)
    require_all = db.Column(db.Boolean, nullable=False, default=False)

    status = db.Column(db.String(20), nullable=False, default=PENDING, index=True)
    decided_at = db.Column(db.DateTime, nullable=True)
    comment = db.Column(db.String(1000), nullable=True)

    # Who actually pressed the button, when that is not the named approver.
    # Both are kept: "approved by Ada on behalf of Ben" is the honest record,
    # and collapsing it to either name alone loses half of it.
    acted_by_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    request = db.relationship("ApprovalRequest", back_populates="steps")

    def public(self, *, labels=None) -> dict:
        labels = labels or {}
        return {
            "id": self.id,
            "level": self.level,
            "approverUserId": self.approver_user_id,
            "approver": labels.get(self.approver_user_id),
            "approverRole": self.approver_role,
            "requireAll": bool(self.require_all),
            "status": self.status,
            "decidedAt": _iso(self.decided_at),
            "comment": self.comment,
            "actedBy": labels.get(self.acted_by_user_id),
            "onBehalf": bool(
                self.acted_by_user_id
                and self.acted_by_user_id != self.approver_user_id
            ),
        }


class ApprovalEvent(db.Model):
    """Everything that happened to one approval request, in order.

    Append-only. The steps say where a request stands; this says how it got
    there, including the things that leave no trace in the steps at all - a
    reminder sent, a question asked, an answer given.
    """
    __tablename__ = "approval_events"

    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    INFO_REQUESTED = "info_requested"
    INFO_PROVIDED = "info_provided"
    DELEGATED = "delegated"
    REMINDED = "reminded"
    CANCELLED = "cancelled"
    LEVEL_COMPLETED = "level_completed"
    ACTIONS = (
        SUBMITTED, APPROVED, REJECTED, INFO_REQUESTED, INFO_PROVIDED,
        DELEGATED, REMINDED, CANCELLED, LEVEL_COMPLETED,
    )

    id = db.Column(db.String, primary_key=True, default=_uuid)
    request_id = db.Column(
        db.String, db.ForeignKey("approval_requests.id"), nullable=False, index=True
    )
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    action = db.Column(db.String(30), nullable=False)
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)
    # Who it concerned, when that differs from who did it.
    target_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)
    level = db.Column(db.Integer, nullable=True)
    comment = db.Column(db.String(1000), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    request = db.relationship("ApprovalRequest", back_populates="events")

    def public(self, *, labels=None) -> dict:
        labels = labels or {}
        return {
            "id": self.id,
            "action": self.action,
            "by": labels.get(self.user_id),
            "target": labels.get(self.target_user_id),
            "level": self.level,
            "comment": self.comment,
            "at": _iso(self.created_at),
        }


class ApprovalDelegation(db.Model):
    """"While I am away, X may approve for me."

    Date-bounded on purpose. An open-ended delegation is how one person
    quietly acquires everybody's authority, and the holiday it was created for
    ended two years ago.

    Delegation is resolved when a decision is made, not when the chain is
    built, so going away after a request was raised still works - which is the
    case that actually happens.
    """
    __tablename__ = "approval_delegations"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    from_user_id = db.Column(
        db.String, db.ForeignKey("users.id"), nullable=False, index=True
    )
    to_user_id = db.Column(
        db.String, db.ForeignKey("users.id"), nullable=False, index=True
    )
    # ISO dates, inclusive, same text form as the order dates elsewhere.
    starts_on = db.Column(db.String(40), nullable=True)
    ends_on = db.Column(db.String(40), nullable=True)
    reason = db.Column(db.String(500), nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)

    def public(self, *, labels=None) -> dict:
        labels = labels or {}
        return {
            "id": self.id,
            "fromUserId": self.from_user_id,
            "from": labels.get(self.from_user_id),
            "toUserId": self.to_user_id,
            "to": labels.get(self.to_user_id),
            "startsOn": self.starts_on,
            "endsOn": self.ends_on,
            "reason": self.reason,
            "active": bool(self.active),
            "createdAt": _iso(self.created_at),
        }


class SupplierPayment(db.Model):
    """Money paid to a supplier against an invoice. A RECORD, not an instruction.

    Not to be confused with `Payment`, which is the opposite direction: what a
    customer pays InvoiceParsed for their subscription. This table is what the
    customer pays their own suppliers.

    **This product initiates no payments and holds no payment credentials.**
    Somebody pays an invoice through their bank and records here that they did.
    That boundary is deliberate and is worth defending: the moment software can
    move money out of a business, it becomes the most valuable thing in the
    building to compromise, and every control around it has to be an order of
    magnitude stronger than anything else here.

    `source` and `provider_reference` exist so a later integration can record
    what it saw without a migration. Nothing reads them yet.
    """
    __tablename__ = "supplier_payments"

    BANK_TRANSFER = "bank_transfer"
    CARD = "card"
    CASH = "cash"
    CHEQUE = "cheque"
    DIRECT_DEBIT = "direct_debit"
    OTHER = "other"
    METHODS = (BANK_TRANSFER, CARD, CASH, CHEQUE, DIRECT_DEBIT, OTHER)

    MANUAL = "manual"
    IMPORTED = "imported"
    SOURCES = (MANUAL, IMPORTED)

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    extraction_id = db.Column(
        db.String, db.ForeignKey("extractions.id"), nullable=False, index=True
    )
    # Denormalized from the invoice so "what have we paid Acme this year" does
    # not need a join through every document.
    supplier_id = db.Column(
        db.String, db.ForeignKey("suppliers.id"), nullable=True, index=True
    )

    # Numeric, never Float. A payment is money.
    amount = db.Column(db.Numeric(18, 4), nullable=False)
    currency = db.Column(db.String(10), nullable=True)
    # ISO text, the same form as the invoice dates it is compared against.
    paid_on = db.Column(db.String(40), nullable=True, index=True)
    method = db.Column(db.String(30), nullable=False, default=BANK_TRANSFER)
    # The bank's reference. What a payment is actually traced by when a
    # supplier says they never received it, and what P2.7 reconciles against.
    reference = db.Column(db.String(200), nullable=True, index=True)
    notes = db.Column(db.String(500), nullable=True)

    source = db.Column(db.String(20), nullable=False, default=MANUAL)
    provider_reference = db.Column(db.String(200), nullable=True)

    recorded_by_user_id = db.Column(
        db.String, db.ForeignKey("users.id"), nullable=True
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Voided, never deleted: a payment recorded in error is a thing somebody
    # asserted, and the correction is part of the record.
    voided_at = db.Column(db.DateTime, nullable=True, index=True)
    voided_by_user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)
    void_reason = db.Column(db.String(500), nullable=True)

    @property
    def is_void(self) -> bool:
        return self.voided_at is not None

    def public(self, *, recorded_by=None, voided_by=None) -> dict:
        return {
            "id": self.id,
            "extractionId": self.extraction_id,
            "supplierId": self.supplier_id,
            "amount": as_json(self.amount),
            "currency": self.currency,
            "paidOn": self.paid_on,
            "method": self.method,
            "reference": self.reference,
            "notes": self.notes,
            "source": self.source,
            "recordedBy": recorded_by,
            "createdAt": _iso(self.created_at),
            "void": self.is_void,
            "voidedBy": voided_by,
            "voidedAt": _iso(self.voided_at),
            "voidReason": self.void_reason,
        }


class BankImport(db.Model):
    """One batch of bank transactions brought in, and where they came from.

    Kept as its own row rather than stamped onto each transaction because an
    import is the unit people reason about when something goes wrong: "undo
    the statement I loaded twice" is a sentence about a batch.

    Two sources, and the first is the point: a bank statement that has already
    been EXTRACTED by the existing statement pipeline can be imported straight
    from it. Re-parsing the same PDF with a second, worse parser would be a
    duplicate of `statement_schema.py` that drifts from it.
    """
    __tablename__ = "bank_imports"

    FROM_EXTRACTION = "extraction"
    FROM_CSV = "csv"
    FROM_XLSX = "xlsx"
    SOURCES = (FROM_EXTRACTION, FROM_CSV, FROM_XLSX)

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    source = db.Column(db.String(20), nullable=False, default=FROM_CSV)
    extraction_id = db.Column(
        db.String, db.ForeignKey("extractions.id"), nullable=True, index=True
    )
    file_name = db.Column(db.String(255), nullable=True)

    bank_name = db.Column(db.String(200), nullable=True)
    account_number = db.Column(db.String(120), nullable=True)
    currency = db.Column(db.String(10), nullable=True)
    period_start = db.Column(db.String(40), nullable=True)
    period_end = db.Column(db.String(40), nullable=True)
    opening_balance = db.Column(db.Numeric(18, 4), nullable=True)
    closing_balance = db.Column(db.Numeric(18, 4), nullable=True)

    transaction_count = db.Column(db.Integer, nullable=False, default=0)
    # Rows that were already present and were therefore NOT imported. Counted
    # rather than silently dropped: "I imported 200 lines and 198 appeared" is
    # alarming unless the system says why.
    duplicate_count = db.Column(db.Integer, nullable=False, default=0)

    imported_by_user_id = db.Column(
        db.String, db.ForeignKey("users.id"), nullable=True
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    transactions = db.relationship(
        "BankTransaction",
        back_populates="bank_import",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def public(self, *, imported_by=None) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "extractionId": self.extraction_id,
            "fileName": self.file_name,
            "bankName": self.bank_name,
            "accountNumber": self.account_number,
            "currency": self.currency,
            "periodStart": self.period_start,
            "periodEnd": self.period_end,
            "openingBalance": as_json(self.opening_balance),
            "closingBalance": as_json(self.closing_balance),
            "transactionCount": self.transaction_count,
            "duplicateCount": self.duplicate_count,
            "importedBy": imported_by,
            "createdAt": _iso(self.created_at),
        }


class BankTransaction(db.Model):
    """One line from a bank statement.

    `debit` and `credit` are kept as the statement presents them rather than
    collapsed into one signed amount, because which column a figure sits in is
    the statement's own assertion about direction, and re-deriving it from a
    sign is how an inbound refund gets reconciled against an outbound payment.

    `fingerprint` is what makes importing the same statement twice harmless.
    """
    __tablename__ = "bank_transactions"
    __table_args__ = (
        # The same line, in the same account, on the same day, for the same
        # amount, with the same description is the same transaction. A bank
        # CAN legitimately produce two identical lines, which is why the
        # fingerprint includes the row's position within its import.
        db.UniqueConstraint(
            "organization_id", "fingerprint", name="uq_bank_txn_fingerprint"
        ),
    )

    UNMATCHED = "unmatched"
    MATCHED = "matched"
    IGNORED = "ignored"
    STATUSES = (UNMATCHED, MATCHED, IGNORED)

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    bank_import_id = db.Column(
        db.String, db.ForeignKey("bank_imports.id"), nullable=False, index=True
    )

    # ISO text, the same form as every other date in this codebase, so they
    # compare without a parsing layer between them.
    txn_date = db.Column(db.String(40), nullable=True, index=True)
    description = db.Column(db.String(500), nullable=True)
    reference = db.Column(db.String(200), nullable=True, index=True)
    debit = db.Column(db.Numeric(18, 4), nullable=True)
    credit = db.Column(db.Numeric(18, 4), nullable=True)
    balance = db.Column(db.Numeric(18, 4), nullable=True)
    currency = db.Column(db.String(10), nullable=True)

    fingerprint = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default=UNMATCHED,
                       index=True)
    # Why a line was set aside: bank charges, interest, a transfer between own
    # accounts. Kept so "unmatched" stays a short list of real problems.
    ignore_reason = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    bank_import = db.relationship("BankImport", back_populates="transactions")

    def public(self) -> dict:
        return {
            "id": self.id,
            "bankImportId": self.bank_import_id,
            "date": self.txn_date,
            "description": self.description,
            "reference": self.reference,
            "debit": as_json(self.debit),
            "credit": as_json(self.credit),
            "balance": as_json(self.balance),
            "currency": self.currency,
            "status": self.status,
            "ignoreReason": self.ignore_reason,
        }


class BankMatch(db.Model):
    """A bank line tied to a payment the organization recorded.

    Suggested by the engine, confirmed by a person. Only a CONFIRMED match
    reconciles anything — the same rule as an invoice match not consuming an
    order's value until somebody has looked at it, and for the same reason: a
    plausible guess nobody checked is not evidence.
    """
    __tablename__ = "bank_matches"
    __table_args__ = (
        # One live match per transaction. "Which payment was this" has to have
        # one answer or a reconciliation is not a reconciliation.
        db.UniqueConstraint(
            "bank_transaction_id", name="uq_bank_match_transaction"
        ),
    )

    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    STATUSES = (SUGGESTED, CONFIRMED, REJECTED)

    # How the pair was found, strongest first.
    BY_REFERENCE = "reference"
    BY_AMOUNT_DATE = "amount_date"
    BY_AMOUNT = "amount"
    BY_FUZZY = "fuzzy"
    BY_MANUAL = "manual"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    organization_id = db.Column(
        db.String, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    bank_transaction_id = db.Column(
        db.String, db.ForeignKey("bank_transactions.id"), nullable=False,
        index=True,
    )
    supplier_payment_id = db.Column(
        db.String, db.ForeignKey("supplier_payments.id"), nullable=False,
        index=True,
    )

    status = db.Column(db.String(20), nullable=False, default=SUGGESTED,
                       index=True)
    method = db.Column(db.String(30), nullable=False, default=BY_MANUAL)
    score = db.Column(db.Float, nullable=False, default=0.0)
    # The gap between the bank line and the payment, when they do not agree
    # exactly. Stored so a part-settled or short-paid line is visible as a
    # figure rather than a feeling.
    difference = db.Column(db.Numeric(18, 4), nullable=True)
    note = db.Column(db.String(500), nullable=True)

    confirmed_by_user_id = db.Column(
        db.String, db.ForeignKey("users.id"), nullable=True
    )
    confirmed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def public(self, *, transaction=None, payment=None, confirmed_by=None) -> dict:
        data = {
            "id": self.id,
            "bankTransactionId": self.bank_transaction_id,
            "supplierPaymentId": self.supplier_payment_id,
            "status": self.status,
            "method": self.method,
            "score": self.score,
            "difference": as_json(self.difference),
            "note": self.note,
            "confirmedBy": confirmed_by,
            "confirmedAt": _iso(self.confirmed_at),
            "createdAt": _iso(self.created_at),
        }
        if transaction is not None:
            data["transaction"] = transaction.public()
        if payment is not None:
            data["payment"] = payment.public()
        return data


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
