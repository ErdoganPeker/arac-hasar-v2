/**
 * SystemTray — installs a Tauri tray icon with Show/Hide/Quit menu and a
 * left-click handler that brings the main window forward.
 *
 * Listens for "single-instance" emitter events so a second launch refocuses the window.
 */
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { TrayIcon } from '@tauri-apps/api/tray';
import { Menu, MenuItem } from '@tauri-apps/api/menu';
import { defaultWindowIcon } from '@tauri-apps/api/app';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { listen } from '@tauri-apps/api/event';

const isTauri = () => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
const TRAY_ID = 'hasarui-main-tray';

export function SystemTray() {
  const { t } = useTranslation();

  useEffect(() => {
    if (!isTauri()) return;
    let tray: TrayIcon | null = null;
    let unlisten: (() => void) | null = null;

    (async () => {
      try {
        const win = getCurrentWindow();

        // Refocus on second-instance launch.
        unlisten = await listen('single-instance', async () => {
          await win.show();
          await win.unminimize();
          await win.setFocus();
        });

        const menu = await Menu.new({
          items: [
            await MenuItem.new({
              id: 'tray-show',
              text: t('tray.show'),
              action: async () => {
                await win.show();
                await win.unminimize();
                await win.setFocus();
              },
            }),
            await MenuItem.new({
              id: 'tray-hide',
              text: t('tray.hide'),
              action: async () => {
                await win.hide();
              },
            }),
            await MenuItem.new({
              id: 'tray-quit',
              text: t('tray.quit'),
              action: async () => {
                // Best-effort exit: try the app handle (most reliable across Tauri 2 versions),
                // then fall back to closing the main window.
                try {
                  const { getAllWindows } = await import('@tauri-apps/api/window');
                  for (const w of await getAllWindows()) await w.close();
                } catch {
                  /* ignored */
                }
              },
            }),
          ],
        });

        tray = await TrayIcon.new({
          id: TRAY_ID,
          tooltip: 'Hasarİ',
          icon: (await defaultWindowIcon()) ?? undefined,
          menu,
          menuOnLeftClick: false,
          action: async (event) => {
            if (event.type === 'Click' && event.button === 'Left' && event.buttonState === 'Up') {
              await win.show();
              await win.unminimize();
              await win.setFocus();
            }
          },
        });
      } catch (e) {
        // tray may already exist from a previous HMR mount — ignore
        console.warn('SystemTray install warning:', e);
      }
    })();

    return () => {
      unlisten?.();
      tray?.close().catch(() => undefined);
    };
  }, [t]);

  return null;
}

export default SystemTray;
