// Try-before-signup plumbing: hold the claim token for a demo extraction run by
// an anonymous visitor, then adopt it into whichever account they end up in.
//
// The token is single-use server-side, so claiming is safe to attempt on every
// sign-in; an unknown or expired token simply reports nothing-to-claim.
import { api } from "./api";
import { track, EVENTS } from "./analytics";

const KEY = "ia_demo_claim";

export function saveClaimToken(token) {
  if (!token) return;
  try {
    localStorage.setItem(KEY, token);
  } catch {
    /* private mode / blocked storage — the demo result just isn't claimable */
  }
}

export function peekClaimToken() {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function clearClaimToken() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

/**
 * Adopt a pending demo extraction into the signed-in account. No-ops when there
 * is no token. Returns the claimed extraction, or null.
 */
export async function claimPendingDemo() {
  const token = peekClaimToken();
  if (!token) return null;
  try {
    const { data } = await api.post("/api/demo/claim", { token });
    // Consume the token either way: if the server didn't recognise it, retrying
    // on every page load would never start working.
    clearClaimToken();
    if (data?.claimed) {
      track(EVENTS.DEMO_CLAIMED, { docType: data.extraction?.docType });
      return data.extraction;
    }
    return null;
  } catch {
    // Network/auth hiccup — keep the token and try again on the next sign-in.
    return null;
  }
}
