// ===================== FRONTEND: auth state =====================
// A tiny auth context: holds the current user (with effective permissions), plus
// login/logout. `can(formCode, action)` is the frontend mirror of the backend's
// PermissionService — used to gate nav items and buttons. The server still
// enforces permissions; this is only for UX.

import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from "react";
import type { ReactNode } from "react";
import { authApi, hasToken } from "./authApi";
import type { Me } from "./authApi";

type Action = "view" | "create" | "edit" | "delete" | "save" | "update" | "export";

interface AuthContextValue {
  user: Me | null;
  loading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  can: (formCode: string, action?: Action) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMe = useCallback(async () => {
    try {
      setUser(await authApi.me());
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (hasToken()) loadMe();
    else setLoading(false);
  }, [loadMe]);

  // The transport layer fires "auth:expired" when a refresh fails — drop the
  // user so route guards bounce back to /login.
  useEffect(() => {
    const onExpired = () => setUser(null);
    window.addEventListener("auth:expired", onExpired);
    return () => window.removeEventListener("auth:expired", onExpired);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    setError(null);
    try {
      await authApi.login(username, password);
      await loadMe();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
      throw e;
    }
  }, [loadMe]);

  const logout = useCallback(() => {
    authApi.logout();
    setUser(null);
  }, []);

  const can = useCallback((formCode: string, action: Action = "view") => {
    if (!user) return false;
    if (user.is_superuser) return true;
    return Boolean(user.permissions[formCode]?.[action]);
  }, [user]);

  const value = useMemo(
    () => ({ user, loading, error, login, logout, can }),
    [user, loading, error, login, logout, can],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
