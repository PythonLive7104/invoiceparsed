// Mirrors backend/plans.py — used for marketing & billing display.
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
    features: [
      "Unlimited invoices",
      "Multi-file batch upload",
      "Multi-page invoices",
      "REST API access",
      "Webhook integrations",
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
    statementLimit: 300,
    features: [
      "Everything in Pro",
      "Unlimited invoices & receipts",
      "300 bank statements / month",
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
