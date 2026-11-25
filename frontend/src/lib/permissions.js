/**
 * Permission names, matching backend/roles.py.
 *
 * Only the names are duplicated here, never the role→permission mapping. The
 * mapping arrives from the server on every `/api/auth/me` (see `can()` in
 * auth.jsx), so there is nothing here to fall out of step with the backend —
 * a stale name simply makes `can()` return false, which hides a control rather
 * than exposing one.
 *
 * Hiding a control is a courtesy, not a security boundary: the server checks
 * every one of these again on the request.
 */
export const PERMISSIONS = {
  documentsWrite: "documents:write",
  documentsDelete: "documents:delete",
  documentsExport: "documents:export",

  suppliersRead: "suppliers:read",
  suppliersWrite: "suppliers:write",
  supplierBankRead: "suppliers:bank:read",

  purchaseOrdersRead: "purchase_orders:read",
  purchaseOrdersWrite: "purchase_orders:write",

  goodsReceiptsRead: "goods_receipts:read",
  goodsReceiptsWrite: "goods_receipts:write",

  approvalsRead: "approvals:read",
  approvalsAct: "approvals:act",

  paymentsRead: "payments:read",
  paymentsWrite: "payments:write",
  reconciliation: "reconciliation:write",

  membersManage: "members:manage",
  billingManage: "billing:manage",
  organizationSettings: "organization:settings",
};
