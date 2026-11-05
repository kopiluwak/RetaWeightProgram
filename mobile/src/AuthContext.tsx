// Auth/session state for the app. Decides which stack to show:
// signed-out -> auth screens; signed-in but not onboarded -> onboarding; else home.
import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { AuthApi, Me, UserApi } from "./api";
import { getAccessToken } from "./tokenStore";

type AuthState = {
  loading: boolean;
  me: Me | null;
  refreshMe: () => Promise<void>;
  signOut: () => Promise<void>;
  clearSession: () => void;
};

const AuthContext = createContext<AuthState | undefined>(undefined);

/** Loads /me on mount (if a token exists) and exposes session state + actions. */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [me, setMe] = useState<Me | null>(null);

  const refreshMe = useCallback(async () => {
    const token = await getAccessToken();
    if (!token) {
      setMe(null);
      return;
    }
    try {
      setMe(await UserApi.me());
    } catch {
      setMe(null);
    }
  }, []);

  const signOut = useCallback(async () => {
    await AuthApi.logout();
    setMe(null);
  }, []);

  /** Drop the session locally without calling /auth/logout.
   *  Used after account deletion is requested: the server has already revoked
   *  every token, so calling logout would just 401. */
  const clearSession = useCallback(() => setMe(null), []);

  useEffect(() => {
    (async () => {
      await refreshMe();
      setLoading(false);
    })();
  }, [refreshMe]);

  return (
    <AuthContext.Provider value={{ loading, me, refreshMe, signOut, clearSession }}>
      {children}
    </AuthContext.Provider>
  );
}

/** Access the auth state; must be called under an AuthProvider. */
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
