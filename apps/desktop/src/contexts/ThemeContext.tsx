/**
 * Theme provider — persists choice to Tauri Store and applies it via `theme.ts`.
 * The actual CSS class toggle on `<html>` happens in `applyTheme`.
 */
import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { applyTheme, type ThemeMode } from '@/lib/theme';
import { loadSettings, saveSetting } from '@/lib/settings';

interface ThemeContextValue {
  mode: ThemeMode;
  setMode: (m: ThemeMode) => Promise<void>;
  toggle: () => Promise<void>;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>('system');

  useEffect(() => {
    let mounted = true;
    (async () => {
      const s = await loadSettings();
      if (!mounted) return;
      setModeState(s.theme);
      applyTheme(s.theme);
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const setMode = useCallback(async (m: ThemeMode) => {
    setModeState(m);
    applyTheme(m);
    await saveSetting('theme', m);
  }, []);

  const toggle = useCallback(async () => {
    // light → dark → system → light
    const next: ThemeMode = mode === 'light' ? 'dark' : mode === 'dark' ? 'system' : 'light';
    await setMode(next);
  }, [mode, setMode]);

  const value = useMemo<ThemeContextValue>(() => ({ mode, setMode, toggle }), [mode, setMode, toggle]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
  return ctx;
}
