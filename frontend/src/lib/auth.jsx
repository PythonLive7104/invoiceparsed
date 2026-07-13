import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, setToken, getToken, apiError } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
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
      setUsage(data.usage);
    } catch {
      setToken(null);
      setUser(null);
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
    setUsage(null);
  }, []);

  const deleteAccount = useCallback(async () => {
    await api.delete("/api/auth/account");
    setToken(null);
    setUser(null);
    setUsage(null);
  }, []);

  // Returns the refreshed user so callers can act on it without waiting for the
  // context re-render (the checkout return page polls for the plan to flip).
  const refreshUsage = useCallback(async () => {
    try {
      const { data } = await api.get("/api/auth/me");
      setUser(data.user);
      setUsage(data.usage);
      return data.user;
    } catch {
      return null;
    }
  }, []);

  const value = {
    user,
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
