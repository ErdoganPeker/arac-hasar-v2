/**
 * Global keyboard shortcuts:
 *   Ctrl+N → /inspect
 *   Ctrl+O → trigger file picker (emits a custom event the active page listens to)
 *   Ctrl+, → /settings
 *   F11    → toggle fullscreen
 *
 * Uses `event.metaKey` on macOS as the Cmd equivalent of Ctrl.
 */
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getCurrentWindow } from '@tauri-apps/api/window';

const isTauri = () => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

export function KeyboardShortcuts() {
  const navigate = useNavigate();

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const mod = e.ctrlKey || e.metaKey;
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      const inField = tag === 'input' || tag === 'textarea' || tag === 'select';

      if (mod && e.key.toLowerCase() === 'n' && !inField) {
        e.preventDefault();
        navigate('/inspect');
        return;
      }
      if (mod && e.key.toLowerCase() === 'o' && !inField) {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent('hasarui:open-file-shortcut'));
        return;
      }
      if (mod && e.key === ',') {
        e.preventDefault();
        navigate('/settings');
        return;
      }
      if (e.key === 'F11') {
        e.preventDefault();
        if (isTauri()) {
          (async () => {
            const w = getCurrentWindow();
            const isFs = await w.isFullscreen();
            await w.setFullscreen(!isFs);
          })();
        } else if (document.fullscreenElement) {
          document.exitFullscreen();
        } else {
          document.documentElement.requestFullscreen?.();
        }
      }
    }
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [navigate]);

  return null;
}

export default KeyboardShortcuts;
