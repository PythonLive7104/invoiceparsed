"""Route blueprints for the InvoiceParsed API."""
from .approval_routes import approval_bp
from .auth_routes import auth_bp
from .billing_routes import billing_bp
from .demo_routes import demo_bp
from .extract_routes import extract_bp
from .goods_receipt_routes import goods_receipt_bp
from .keys_routes import keys_bp
from .match_routes import match_bp
from .organization_routes import organization_bp
from .payment_routes import payment_bp
from .purchase_order_routes import purchase_order_bp
from .reconciliation_routes import reconciliation_bp
from .supplier_routes import supplier_bp
from .support_routes import support_bp
from .webhook_routes import webhook_bp

__all__ = [
    "approval_bp",
    "auth_bp",
    "billing_bp",
    "demo_bp",
    "extract_bp",
    "goods_receipt_bp",
    "keys_bp",
    "match_bp",
    "organization_bp",
    "payment_bp",
    "reconciliation_bp",
    "purchase_order_bp",
    "supplier_bp",
    "support_bp",
    "webhook_bp",
]
