import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { UserRead } from "../api/contracts";
import { clearAccessToken, readAccessToken, writeAccessToken } from "./authStorage";

type AuthStatus = "loading" | "authenticated" | "anonymous" | "unavailable";

interface AuthContextValue {
  user: UserRead | null;
  status: AuthStatus;
  sessionExpired: boolean;
  sessionError: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  retrySession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<UserRead | null>(null);
  const [status, setStatus] = useState<AuthStatus>(() => (readAccessToken() ? "loading" : "anonymous"));
  const [sessionExpired, setSessionExpired] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);

  const clearSession = useCallback(
    (expired = false) => {
      clearAccessToken();
      queryClient.clear();
      setUser(null);
      setStatus("anonymous");
      setSessionExpired(expired);
      setSessionError(null);
    },
    [queryClient],
  );

  const restoreSession = useCallback(async () => {
    if (!readAccessToken()) {
      setUser(null);
      setStatus("anonymous");
      return;
    }
    setStatus("loading");
    setSessionError(null);
    try {
      const currentUser = await api.auth.me();
      setUser(currentUser);
      setStatus("authenticated");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearSession(true);
        return;
      }
      setStatus("unavailable");
      setSessionError(error instanceof Error ? error.message : "The current session could not be restored.");
    }
  }, [clearSession]);

  useEffect(() => {
    if (!readAccessToken()) return;
    let cancelled = false;
    api.auth.me().then((currentUser) => {
      if (!cancelled) {
        setUser(currentUser);
        setStatus("authenticated");
      }
    }).catch((error: unknown) => {
      if (cancelled) return;
      if (error instanceof ApiError && error.status === 401) {
        clearSession(true);
        return;
      }
      setStatus("unavailable");
      setSessionError(error instanceof Error ? error.message : "The current session could not be restored.");
    });
    return () => { cancelled = true; };
  }, [clearSession]);

  useEffect(() => {
    const onUnauthorized = () => clearSession(true);
    window.addEventListener("verifia:unauthorized", onUnauthorized);
    return () => window.removeEventListener("verifia:unauthorized", onUnauthorized);
  }, [clearSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      queryClient.clear();
      setStatus("loading");
      setSessionExpired(false);
      setSessionError(null);
      try {
        const token = await api.auth.login(email, password);
        writeAccessToken(token.access_token);
        const currentUser = await api.auth.me();
        setUser(currentUser);
        setStatus("authenticated");
      } catch (error) {
        clearAccessToken();
        setUser(null);
        setStatus("anonymous");
        throw error;
      }
    },
    [queryClient],
  );

  const logout = useCallback(() => {
    if (readAccessToken()) void api.auth.logout().catch(() => undefined);
    clearSession(false);
  }, [clearSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      sessionExpired,
      sessionError,
      login,
      logout,
      retrySession: restoreSession,
    }),
    [user, status, sessionExpired, sessionError, login, logout, restoreSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}
