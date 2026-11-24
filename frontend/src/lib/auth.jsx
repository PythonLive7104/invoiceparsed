import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, setToken, getToken, apiError } from "./api";
import { claimPendingDemo } from "./demo";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // The organization this session is acting as, and the list the user belongs
  // to. The PLAN lives here, not on the user: a team shares one allowance.
  const [organization, setOrganization] = useState(null);
  const [organizations, setOrganizations] = useState([]);
  // What this member may do in the acting organization, as the server reports
  // it. Held as data rather than derived from the role here: a copy of the
  // role table in the frontend would drift from the backend's, and the drift
  // would surface either as a button that 403s or as a control the server
  // allows that the UI has silently hidden.
  const [permissions, setPermissions] = useState([]);
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setUsage(null);
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get("/api/auth/me");
      setUser(data.user);
      setOrganization(data.organization ?? null);
      setOrganizations(data.organizations ?? []);
      setPermissions(data.permissions ?? []);
      setUsage(data.usage);
      // If they ran an extraction on the landing page before signing up, adopt
      // it into this account now. No-ops when there's no pending demo. Kept
      // non-fatal: a hiccup here must not invalidate an otherwise good session.
      try {
        if (await claimPendingDemo()) {
          const { data: fresh } = await api.get("/api/auth/me");
          setUsage(fresh.usage);
        }
      } catch {
        /* the claim is a bonus, never a reason to sign someone out */
      }
    } catch {
      setToken(null);
      setUser(null);
      setOrganization(null);
      setOrganizations([]);
      setPermissions([]);
      setUsage(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  const login = useCallback(async (email, password) => {
    const { data } = await api.post("/api/auth/login", { email, password });
    setToken(data.token);
    setUser(data.user);
    await loadMe();
  }, [loadMe]);

  // Registration no longer signs the user in — they must confirm their email
  // first. Returns the response so the form can show a "check your inbox" state.
  const register = useCallback(async (name, email, password) => {
    const { data } = await api.post("/api/auth/register", { name, email, password });
    return data;
  }, []);

  const loginWithGoogle = useCallback(async (credential) => {
    const { data } = await api.post("/api/auth/google", { credential });
    setToken(data.token);
    setUser(data.user);
    await loadMe();
  }, [loadMe]);

  // Adopt a JWT handed back by the Google redirect flow (token in URL fragment).
  // Returns true on success so the callback page can route accordingly.
  const adoptToken = useCallback(async (token) => {
    setToken(token);
    try {
      const { data } = await api.get("/api/auth/me");
      setUser(data.user);
      setOrganization(data.organization ?? null);
      setOrganizations(data.organizations ?? []);
      setPermissions(data.permissions ?? []);
      setUsage(data.usage);
      return true;
    } catch {
      setToken(null);
      setUser(null);
      return false;
    }
  }, []);

  // Confirm an email/password account from the emailed link, then sign in.
  const verifyEmail = useCallback(async (token) => {
    const { data } = await api.post("/api/auth/verify-email", { token });
    setToken(data.token);
    setUser(data.user);
    await loadMe();
  }, [loadMe]);

  const resendVerification = useCallback(async (email) => {
    await api.post("/api/auth/resend-verification", { email });
  }, []);

  const forgotPassword = useCallback(async (email) => {
    await api.post("/api/auth/forgot-password", { email });
  }, []);

  const resetPassword = useCallback(async (token, password) => {
    const { data } = await api.post("/api/auth/reset-password", { token, password });
    setToken(data.token);
    setUser(data.user);
    await loadMe();
  }, [loadMe]);

  const updateProfile = useCallback(async (name) => {
    const { data } = await api.patch("/api/auth/profile", { name });
    setUser(data.user);
  }, []);

  const changePassword = useCallback(async (currentPassword, newPassword) => {
    await api.post("/api/auth/change-password", { currentPassword, newPassword });
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setOrganization(null);
    setOrganizations([]);
    setPermissions([]);
    setUsage(null);
  }, []);

  const deleteAccount = useCallback(async () => {
    await api.delete("/api/auth/account");
    setToken(null);
    setUser(null);
    setOrganization(null);
    setOrganizations([]);
    setPermissions([]);
    setUsage(null);
  }, []);

  // Returns the refreshed ORGANIZATION so callers can act on it without waiting
  // for the context re-render. The checkout return page polls for the plan to
  // flip, and the plan is on the organization.
  const refreshUsage = useCallback(async () => {
    try {
      const { data } = await api.get("/api/auth/me");
      setUser(data.user);
      setOrganization(data.organization ?? null);
      setOrganizations(data.organizations ?? []);
      setPermissions(data.permissions ?? []);
      setUsage(data.usage);
      return data.organization ?? null;
    } catch {
      return null;
    }
  }, []);

  const value = {
    user,
    organization,
    organizations,
    permissions,
    /** Does the acting member hold this permission? Unknown permission names
     *  answer false, so a control for a capability this server does not have
     *  stays hidden rather than appearing for everyone. */
    can: (permission) => permissions.includes(permission),
    /** Does the acting organization's PLAN include this capability?
     *
     *  Separate from `can()`, and both are needed, because they answer
     *  different questions: `can` is "may this person", `has` is "has this
     *  organization bought it". A control the plan does not include should
     *  offer an upgrade; a control the role does not allow should not appear.
     *
     *  Read from the server's capability list on every `/me`, so there is no
     *  copy of the plan table here to fall out of step with plans.py. An
     *  unknown name answers false, which locks a control rather than
     *  unlocking one. */
    has: (capability) => Boolean(usage?.capabilities?.[capability]),
    // Convenience: the acting organization's plan. Read this rather than
    // user.plan, which no longer exists.
    plan: organization?.plan ?? "free",
    usage,
    loading,
    login,
    register,
    loginWithGoogle,
    adoptToken,
    verifyEmail,
    resendVerification,
    forgotPassword,
    resetPassword,
    updateProfile,
    changePassword,
    deleteAccount,
    logout,
    refreshUsage,
    setUsage,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export { apiError };
