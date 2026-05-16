/**
 * WindowFileDrop — relays Tauri window-level file-drop events to the page.
 *
 * When the user drags files from the OS file manager onto the window, Tauri
 * emits a `tauri://drag-drop` event with the absolute paths. We re-emit a
 * DOM-level `hasarui:files-dropped` event carrying File objects so individual
 * pages (BatchUploader, InspectPage) can handle it without each subscribing
 * to a Tauri event.
 */
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { pathToFile } from '@/lib/commands';
import { MAX_FILE_SIZE_MB } from '@/lib/file-picker';

const IMAGE_EXT = /\.(jpe?g|png|webp)$/i;
const MAX_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;
const isTauri = () => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

export function WindowFileDrop() {
  const navigate = useNavigate();

  useEffect(() => {
    if (!isTauri()) return;
    const w = getCurrentWindow();
    let unlisten: (() => void) | null = null;
    (async () => {
      unlisten = await w.onDragDropEvent(async (e) => {
        const payload = e.payload as { type: string; paths?: string[] };
        if (payload.type !== 'drop' || !payload.paths) return;
        const paths = payload.paths.filter((p) => IMAGE_EXT.test(p));
        if (paths.length === 0) return;
        try {
          const all = await Promise.all(paths.map((p) => pathToFile(p)));
          const files = all.filter((f) => f.size <= MAX_BYTES);
          const rejected = all
            .filter((f) => f.size > MAX_BYTES)
            .map((f) => ({ name: f.name, size: f.size }));
          if (rejected.length) {
            window.dispatchEvent(
              new CustomEvent('hasarui:file-size-rejected', {
                detail: { rejected, maxMb: MAX_FILE_SIZE_MB },
              }),
            );
          }
          if (!files.length) return;
          window.dispatchEvent(
            new CustomEvent('hasarui:files-dropped', { detail: { files } }),
          );
          // If we're not on inspect/batch, route to inspect for convenience.
          const loc = window.location.pathname;
          if (!loc.startsWith('/inspect') && !loc.startsWith('/batch')) {
            navigate(files.length > 5 ? '/batch' : '/inspect');
          }
        } catch (err) {
          console.warn('Window drop failed:', err);
        }
      });
    })();
    return () => unlisten?.();
  }, [navigate]);

  return null;
}

export default WindowFileDrop;
