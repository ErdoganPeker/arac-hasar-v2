/**
 * Auth state provider.
 * - Bootstraps from the Tauri Store on mount (silent).
 * - Wires `api` so axios interceptors can read tokens / persist refreshes / trigger logout.
 * - Exposes `login`, `register`, `logout`, plus the live `user` / `tokens` for UI gating.
 */
import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { AuthTokens, LoginRequest, RegisterRequest, User } from '@arac-hasar/types';
import { api } from '@/lib/api';
import { clearAuth, loadAuth, saveAuth, updateTokens } from '@/lib/auth-store';

interface AuthContextValue {
  user: User | null;
  tokens: AuthTokens | null;
  ready: boolean;
  login: (payload: LoginRequest) => Promise<void>;
  register: (payload: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [tokens, setTokens] = useState<AuthTokens | null>(null);
  const [ready, setReady] = useState(false);
  const tokensRef = useRef<AuthTokens | null>(null);

  // Keep ref in sync so the axios interceptor always sees the latest.
  useEffect(() => {
    tokensRef.current = tokens;
  }, [tokens]);

  const doLogout = useCallback(async () => {
    await clearAuth();
    setUser(null);
    setTokens(null);
  }, []);

  // Bind api once — interceptor reads tokens via ref so we don't need re-binding.
  useEffect(() => {
    api.bindAuth({
      getTokens: () => tokensRef.current,
      setTokens: async (t) => {
        tokensRef.current = t;
        setTokens(t);
        await updateTokens(t);
      },
      onLogout: doLogout,
    });
  }, [doLogout]);

  // Boot — load persisted session.
  useEffect(() => {
    let mounted = true;
    (async () => {
      const stored = await loadAuth();
      if (mounted && stored) {
        setUser(stored.user);
        setTokens(stored.tokens);
        tokensRef.current = stored.tokens;
      }
      if (mounted) setReady(true);
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const login = useCallback(async (payload: LoginRequest) => {
    const res = await api.login(payload);
    await saveAuth({ user: res.user, tokens: res.tokens });
    tokensRef.current = res.tokens;
    setUser(res.user);
    setTokens(res.tokens);
  }, []);

  const register = useCallback(async (payload: RegisterRequest) => {
    const res = await api.register(payload);
    await saveAuth({ user: res.user, tokens: res.tokens });
    tokensRef.current = res.tokens;
    setUser(res.user);
    setTokens(res.tokens);
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    await doLogout();
  }, [doLogout]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, tokens, ready, login, register, logout }),
    [user, tokens, ready, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
