// Funnel analytics — one thin wrapper over Plausible and/or PostHog.
//
// Both providers are optional and configured purely by env, so with nothing set
// every call here is a no-op (local dev, tests, self-hosters). Scripts are
// injected at runtime rather than hard-coded into index.html so that a build
// without keys ships no third-party requests at all.
//
// The funnel this exists to answer: how many people land, how many try the
// extractor, how many create an account, how many pay.

const PLAUSIBLE_DOMAIN = import.meta.env.VITE_PLAUSIBLE_DOMAIN || "";
// The *manual* script so SPA route changes are counted exactly once, by us.
const PLAUSIBLE_SRC =
  import.meta.env.VITE_PLAUSIBLE_SRC || "https://plausible.io/js/script.manual.js";
const POSTHOG_KEY = import.meta.env.VITE_POSTHOG_KEY || "";
const POSTHOG_HOST = import.meta.env.VITE_POSTHOG_HOST || "https://us.i.posthog.com";
// Log to the console instead of sending — useful while wiring new events up.
const DEBUG = import.meta.env.VITE_ANALYTICS_DEBUG === "true";

/** Canonical event names. Keep this list short: every event here should map to a
 *  step someone actually makes a decision about. */
export const EVENTS = {
  // Landing-page try-before-signup
  DEMO_STARTED: "demo_started",
  DEMO_COMPLETED: "demo_completed",
  DEMO_FAILED: "demo_failed",
  DEMO_EXPORT_BLOCKED: "demo_export_blocked", // hit the signup gate on a result
  DEMO_CLAIMED: "demo_claimed", // a demo result adopted into a new account
  // Accounts
  SIGNUP_SUBMITTED: "signup_submitted",
  SIGNUP_VERIFIED: "signup_verified",
  LOGIN: "login",
  // Product usage
  EXTRACT_STARTED: "extract_started",
  EXTRACT_COMPLETED: "extract_completed",
  // Revenue
  CHECKOUT_STARTED: "checkout_started",
  PAYMENT_SUCCEEDED: "payment_succeeded",
};

let started = false;
// Events fired before a provider script finishes loading are held here.
const queue = [];

function loadScript(src, attrs = {}) {
  const el = document.createElement("script");
  el.src = src;
  el.defer = true;
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  document.head.appendChild(el);
  return el;
}

function initPlausible() {
  if (!PLAUSIBLE_DOMAIN) return;
  // The stub lets us fire events before the script lands; Plausible's own script
  // drains window.plausible.q on load.
  window.plausible =
    window.plausible ||
    function () {
      (window.plausible.q = window.plausible.q || []).push(arguments);
    };
  loadScript(PLAUSIBLE_SRC, { "data-domain": PLAUSIBLE_DOMAIN });
}

function initPostHog() {
  if (!POSTHOG_KEY) return;
  // Minimal stub of the official snippet: queue calls until the real library
  // replaces window.posthog, then it replays them.
  const stub = { _i: [], __SV: 1 };
  for (const name of ["capture", "identify", "init", "register", "reset"]) {
    stub[name] = function () {
      (stub.__q = stub.__q || []).push([name, arguments]);
    };
  }
  window.posthog = window.posthog || stub;
  const el = loadScript(`${POSTHOG_HOST.replace(/\/$/, "")}/static/array.js`);
  el.onload = () => {
    try {
      window.posthog.init(POSTHOG_KEY, {
        api_host: POSTHOG_HOST,
        capture_pageview: false, // we send these ourselves, on route change
        persistence: "localStorage",
      });
      for (const [name, args] of stub.__q || []) window.posthog[name]?.(...args);
    } catch {
      /* analytics must never break the app */
    }
  };
}

/** Call once, as early as possible. Safe to call repeatedly. */
export function initAnalytics() {
  if (started || typeof window === "undefined") return;
  started = true;
  try {
    initPlausible();
    initPostHog();
    for (const fn of queue.splice(0)) fn();
  } catch {
    /* ignore */
  }
}

/** Record a funnel event. `props` values should be low-cardinality (plan, docType…). */
export function track(event, props = {}) {
  if (typeof window === "undefined") return;
  if (DEBUG) {
    console.info("[analytics]", event, props);
    return;
  }
  if (!started) {
    queue.push(() => track(event, props));
    return;
  }
  try {
    window.plausible?.(event, Object.keys(props).length ? { props } : undefined);
    window.posthog?.capture?.(event, props);
  } catch {
    /* ignore */
  }
}

/** Record a pageview for an SPA route change. */
export function trackPageview(path) {
  if (typeof window === "undefined") return;
  if (DEBUG) {
    console.info("[analytics] pageview", path);
    return;
  }
  if (!started) {
    queue.push(() => trackPageview(path));
    return;
  }
  try {
    window.plausible?.("pageview");
    window.posthog?.capture?.("$pageview", { $current_url: window.location.href });
  } catch {
    /* ignore */
  }
}

/** True when at least one provider is configured — handy for conditional UI/debug. */
export const analyticsEnabled = Boolean(PLAUSIBLE_DOMAIN || POSTHOG_KEY);
