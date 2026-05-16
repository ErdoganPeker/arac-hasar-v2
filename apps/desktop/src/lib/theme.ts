/**
 * Theme management — `light` | `dark` | `system`.
 *
 * Applies the `dark` class to `<html>` so Tailwind's `dark:` variants kick in.
 * Subscribes to `prefers-color-scheme` while in `system` mode and updates live.
 */
export type ThemeMode = 'light' | 'dark' | 'system';

const MEDIA = '(prefers-color-scheme: dark)';

function systemPrefersDark(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia(MEDIA).matches;
}

function applyClass(isDark: boolean) {
  if (typeof document === 'undefined') return;
  document.documentElement.classList.toggle('dark', isDark);
  document.documentElement.style.colorScheme = isDark ? 'dark' : 'light';
}

let currentMode: ThemeMode = 'system';
let mediaListener: ((e: MediaQueryListEvent) => void) | null = null;

export function applyTheme(mode: ThemeMode): void {
  currentMode = mode;

  if (typeof window !== 'undefined' && mediaListener) {
    window.matchMedia(MEDIA).removeEventListener('change', mediaListener);
    mediaListener = null;
  }

  if (mode === 'system') {
    applyClass(systemPrefersDark());
    if (typeof window !== 'undefined') {
      mediaListener = (e) => applyClass(e.matches);
      window.matchMedia(MEDIA).addEventListener('change', mediaListener);
    }
  } else {
    applyClass(mode === 'dark');
  }
}

export function getCurrentMode(): ThemeMode {
  return currentMode;
}

export function isCurrentlyDark(): boolean {
  if (typeof document === 'undefined') return false;
  return document.documentElement.classList.contains('dark');
}
