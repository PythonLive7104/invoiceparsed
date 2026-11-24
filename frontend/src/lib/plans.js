// Mirrors backend/plans.py — used for marketing & billing display ONLY.
//
// Display only is load-bearing: the pricing page is prerendered at build time
// and cannot ask the server, so the table is duplicated here. Enforcement
// lives entirely in backend/plans.py and the server's capability list (read in
// the app through `has()` in lib/auth.jsx) — nothing in the product is
// permitted or refused on the strength of this file. Keep the two in step
// anyway: a pricing page promising a capability the backend does not grant is
// a support ticket.
export const PLANS = {
  free: {
    id: "free",
    name: "Free",
    price: 0,
    limit: 5,
    tagline: "Kick the tires. No credit card required.",
    segment: "personal",
    batch: false,
    multiPage: false,
    api: false,
    webhooks: false,
    statements: false,
    payables: false,
    features: [
      "5 invoices / month",
      "PDF & image upload",
      "Excel, CSV & JSON export",
      "Extraction history",
    ],
  },
  starter: {
    id: "starter",
    name: "Starter",
    price: 19,
    limit: 100,
    tagline: "For freelancers drowning in client invoices.",
    highlighted: true,
    segment: "both",
    batch: true,
    multiPage: true,
    api: false,
    webhooks: false,
    statements: false,
    payables: false,
    features: [
      "100 invoices / month",
      "Multi-file batch upload",
      "Multi-page invoices",
      "Excel, CSV & JSON export",
      "Email support",
    ],
  },
  pro: {
    id: "pro",
    name: "Pro",
    price: 49,
    limit: null,
    tagline: "For agencies and developers who automate.",
    segment: "both",
    batch: true,
    multiPage: true,
    api: true,
    webhooks: true,
    statements: false,
    payables: true,
    features: [
      "Everything in Starter",
      "Unlimited invoices & receipts",
      "Suppliers, purchase orders & invoice matching",
      "Approvals with roles & permissions",
      "REST API access + webhooks",
    ],
  },
  business: {
    id: "business",
    name: "Business",
    price: 99,
    limit: null,
    tagline: "For teams and high-volume finance ops.",
    segment: "business",
    batch: true,
    multiPage: true,
    api: true,
    webhooks: true,
    statements: true,
    payables: true,
    statementLimit: 200,
    features: [
      "Everything in Pro",
      "Unlimited invoices & receipts",
      "200 bank statements / month",
      "Centralized billing & invoicing",
      "Priority support + onboarding",
    ],
  },
};

export const PLAN_ORDER = ["free", "starter", "pro", "business"];

/** Plan ids for a given audience track. */
export function plansForSegment(segment) {
  return PLAN_ORDER.filter((id) => {
    const s = PLANS[id].segment;
    return s === "both" || s === segment;
  });
}

/** Whether a plan id unlocks a capability (mirrors backend/plans.py). */
export function planAllows(planId, capability) {
  return Boolean(PLANS[planId]?.[capability]);
}
