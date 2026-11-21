"""Organization roles and permissions.

Permissions are defined as data rather than scattered `if role == "admin"`
checks, so that adding a capability means editing one table and the answer to
"who can do this?" is readable in one place.

Roles are per *membership*, not per user: the same person can be an owner of
their own organization and a read-only viewer in a client's.

Deliberately coarse for now. Several permissions name features that do not
exist yet (purchase orders, goods receipts, approvals) — they are declared here
so the roles are stable as those modules land, and because leaving them out
would mean retrofitting role definitions later and silently widening access in
the meantime. A permission for a feature that does not exist simply never gets
checked.
"""

# ─── Permissions ─────────────────────────────────────────────────────────────
# Documents and extraction
DOCUMENTS_READ = "documents:read"
DOCUMENTS_WRITE = "documents:write"     # upload, edit extracted fields
DOCUMENTS_DELETE = "documents:delete"
DOCUMENTS_EXPORT = "documents:export"   # CSV / XLSX / JSON download

# Accounts payable (Phase 2)
SUPPLIERS_READ = "suppliers:read"
SUPPLIERS_WRITE = "suppliers:write"
SUPPLIER_BANK_READ = "suppliers:bank:read"   # deliberately separate: bank
                                             # details are the highest-value
                                             # target in the whole dataset
PURCHASE_ORDERS_READ = "purchase_orders:read"
PURCHASE_ORDERS_WRITE = "purchase_orders:write"
GOODS_RECEIPTS_READ = "goods_receipts:read"
GOODS_RECEIPTS_WRITE = "goods_receipts:write"
APPROVALS_READ = "approvals:read"
APPROVALS_ACT = "approvals:act"              # approve / reject
PAYMENTS_READ = "payments:read"
PAYMENTS_WRITE = "payments:write"            # record a payment
RECONCILIATION = "reconciliation:write"

# Reporting and intelligence (Phase 4)
REPORTS_READ = "reports:read"
AI_ASSISTANT = "ai:query"

# Administration
MEMBERS_READ = "members:read"
MEMBERS_MANAGE = "members:manage"
BILLING_READ = "billing:read"
BILLING_MANAGE = "billing:manage"
API_KEYS_MANAGE = "api_keys:manage"
WEBHOOKS_MANAGE = "webhooks:manage"
ORG_SETTINGS = "organization:settings"
AUDIT_READ = "audit:read"

# ─── Roles ───────────────────────────────────────────────────────────────────
OWNER = "owner"
ADMIN = "administrator"
FINANCE_MANAGER = "finance_manager"
ACCOUNTANT = "accountant"
PROCUREMENT = "procurement_officer"
DEPARTMENT_MANAGER = "department_manager"
APPROVER = "approver"
VIEWER = "viewer"

ROLE_ORDER = [
    OWNER, ADMIN, FINANCE_MANAGER, ACCOUNTANT, PROCUREMENT,
    DEPARTMENT_MANAGER, APPROVER, VIEWER,
]

_READ_ONLY = {
    DOCUMENTS_READ, SUPPLIERS_READ, PURCHASE_ORDERS_READ, GOODS_RECEIPTS_READ,
    APPROVALS_READ, PAYMENTS_READ, REPORTS_READ,
}

_ACCOUNTANT = _READ_ONLY | {
    DOCUMENTS_WRITE, DOCUMENTS_EXPORT, SUPPLIERS_WRITE,
    PAYMENTS_WRITE, RECONCILIATION, AI_ASSISTANT,
}

_FINANCE_MANAGER = _ACCOUNTANT | {
    DOCUMENTS_DELETE, SUPPLIER_BANK_READ, APPROVALS_ACT,
    PURCHASE_ORDERS_WRITE, BILLING_READ, AUDIT_READ, MEMBERS_READ,
}

_ADMIN = _FINANCE_MANAGER | {
    GOODS_RECEIPTS_WRITE, MEMBERS_MANAGE, BILLING_MANAGE,
    API_KEYS_MANAGE, WEBHOOKS_MANAGE, ORG_SETTINGS,
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    # The owner is the only role that can never be locked out of its own
    # organization, so it gets everything the admin has by definition.
    OWNER: set(_ADMIN),
    ADMIN: set(_ADMIN),
    FINANCE_MANAGER: set(_FINANCE_MANAGER),
    ACCOUNTANT: set(_ACCOUNTANT),
    PROCUREMENT: _READ_ONLY | {
        DOCUMENTS_WRITE, DOCUMENTS_EXPORT, SUPPLIERS_WRITE,
        PURCHASE_ORDERS_WRITE, GOODS_RECEIPTS_WRITE, AI_ASSISTANT,
    },
    DEPARTMENT_MANAGER: _READ_ONLY | {
        DOCUMENTS_WRITE, DOCUMENTS_EXPORT, APPROVALS_ACT, AI_ASSISTANT,
    },
    APPROVER: _READ_ONLY | {APPROVALS_ACT},
    VIEWER: set(_READ_ONLY),
}

# Every role an organization can hand out.
ROLES = tuple(ROLE_ORDER)

# What a brand-new member gets when no role is named. The most restrictive role
# that can still do the product's core job, so an invite cannot accidentally
# grant billing or member management.
DEFAULT_ROLE = ACCOUNTANT


def permissions_for(role: str) -> set[str]:
    """Permissions granted by `role`. An unknown role grants nothing."""
    return ROLE_PERMISSIONS.get(role, set())


def role_allows(role: str, permission: str) -> bool:
    return permission in permissions_for(role)


def is_valid_role(role: str) -> bool:
    return role in ROLE_PERMISSIONS
