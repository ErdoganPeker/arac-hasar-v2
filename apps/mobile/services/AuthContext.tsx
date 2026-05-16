/**
 * services/AuthContext.tsx — React Context for auth state propagation.
 *
 * Wraps token bootstrap on app start and exposes `signIn`, `signOut`,
 * `register`, and the cached current user.
 */
import React, {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { api, LoginPayload, RegisterPayload } from './api';
import {
  AuthUser,
  clearTokens,
  getAccessToken,
  getCachedUser,
  setCachedUser,
} from './auth';

interface AuthContextValue {
  ready: boolean;
  authenticated: boolean;
  user: AuthUser | null;
  signIn: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);

  const bootstrap = useCallback(async () => {
    const token = await getAccessToken();
    if (token) {
      const cached = await getCachedUser();
      if (cached) setUser(cached);
      setAuthenticated(true);
      // Best-effort refresh of profile in background.
      api.auth
        .me()
        .then((me) => {
          if (me?.email) {
            setUser(me as AuthUser);
            setCachedUser(me as AuthUser);
          }
        })
        .catch(() => {
          /* token may have just expired; interceptor will clear if so */
        });
    } else {
      setAuthenticated(false);
      setUser(null);
    }
    setReady(true);
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  const signIn = useCallback(async (payload: LoginPayload) => {
    const res = await api.auth.login(payload);
    if (res?.user) {
      setUser(res.user as AuthUser);
      await setCachedUser(res.user as AuthUser);
    }
    setAuthenticated(true);
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    const res = await api.auth.register(payload);
    if (res?.user) {
      setUser(res.user as AuthUser);
      await setCachedUser(res.user as AuthUser);
    }
    setAuthenticated(true);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.auth.logout();
    } catch {
      /* ignore */
    }
    await clearTokens();
    setAuthenticated(false);
    setUser(null);
  }, []);

  const refresh = useCallback(async () => {
    const me = await api.auth.me().catch(() => null);
    if (me?.email) {
      setUser(me as AuthUser);
      await setCachedUser(me as AuthUser);
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ ready, authenticated, user, signIn, register, signOut, refresh }),
    [ready, authenticated, user, signIn, register, signOut, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside <AuthProvider>');
  }
  return ctx;
}
