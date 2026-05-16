'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useRouter, usePathname } from 'next/navigation';
import {
  auth,
  clearStoredTokens,
  getStoredAccessToken,
  setStoredTokens,
  setUnauthorizedHandler,
  type User,
} from './api';
import { isJwtExpired } from './jwt';

export interface AuthContextValue {
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    password: string,
    fullName: string,
  ) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const bootstrapRan = useRef(false);

  const logout = useCallback(() => {
    clearStoredTokens();
    setUser(null);
    router.push('/login');
  }, [router]);

  // Wire 401 handler from axios interceptor to context-level logout.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      // Only redirect from protected pages to avoid loops on /login.
      if (
        pathname &&
        !pathname.startsWith('/login') &&
        !pathname.startsWith('/register') &&
        pathname !== '/'
      ) {
        router.push('/login');
      }
    });
    return () => setUnauthorizedHandler(null);
  }, [pathname, router]);

  // Bootstrap: if we have a non-expired token, fetch /auth/me.
  useEffect(() => {
    if (bootstrapRan.current) return;
    bootstrapRan.current = true;
    const token = getStoredAccessToken();
    if (!token || isJwtExpired(token, 5)) {
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const me = await auth.me();
        setUser(me);
      } catch {
        // 401 handler will clear tokens and redirect if needed.
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await auth.login(email, password);
      setStoredTokens(res.access_token, res.refresh_token);
      const me = res.user ?? (await auth.me());
      setUser(me);
    },
    [],
  );

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      const res = await auth.register(email, password, fullName);
      setStoredTokens(res.access_token, res.refresh_token);
      setUser(res.user);
    },
    [],
  );

  const refreshUser = useCallback(async () => {
    try {
      const me = await auth.me();
      setUser(me);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isAuthenticated: !!user,
      isAdmin: user?.role === 'admin',
      login,
      register,
      logout,
      refreshUser,
    }),
    [user, loading, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
