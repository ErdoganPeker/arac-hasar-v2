/**
 * AppMenu — installs the native Tauri application menu (top menu bar).
 *
 * Mac shows a real menu bar; Windows/Linux get the in-window menu via the
 * window decorations. On web (Vite dev outside Tauri) the component renders an
 * inline HTML menu strip so the same items are still reachable for testing.
 *
 * Events:
 *  - The Rust side doesn't dispatch routes; the menu handlers call React Router
 *    via the provided `navigate` callback. Tauri actions (fullscreen, quit) are
 *    invoked via the JS API.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { Menu, MenuItem, PredefinedMenuItem, Submenu } from '@tauri-apps/api/menu';

const isTauri = () => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

export function AppMenu() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  useEffect(() => {
    if (!isTauri()) return;
    let installed: Menu | null = null;

    (async () => {
      try {
        const fileMenu = await Submenu.new({
          text: t('appMenu.file'),
          items: [
            await MenuItem.new({
              id: 'new-inspection',
              text: t('appMenu.newInspection'),
              accelerator: 'CmdOrCtrl+N',
              action: () => navigate('/inspect'),
            }),
            await MenuItem.new({
              id: 'open-file',
              text: t('appMenu.openFile'),
              accelerator: 'CmdOrCtrl+O',
              action: () =>
                window.dispatchEvent(new CustomEvent('hasarui:open-file-shortcut')),
            }),
            await PredefinedMenuItem.new({ item: 'Separator' }),
            await MenuItem.new({
              id: 'preferences',
              text: t('appMenu.preferences'),
              accelerator: 'CmdOrCtrl+,',
              action: () => navigate('/settings'),
            }),
            await PredefinedMenuItem.new({ item: 'Separator' }),
            await PredefinedMenuItem.new({ item: 'Quit', text: t('appMenu.quit') }),
          ],
        });

        const editMenu = await Submenu.new({
          text: t('appMenu.edit'),
          items: [
            await PredefinedMenuItem.new({ item: 'Undo' }),
            await PredefinedMenuItem.new({ item: 'Redo' }),
            await PredefinedMenuItem.new({ item: 'Separator' }),
            await PredefinedMenuItem.new({ item: 'Cut' }),
            await PredefinedMenuItem.new({ item: 'Copy' }),
            await PredefinedMenuItem.new({ item: 'Paste' }),
            await PredefinedMenuItem.new({ item: 'SelectAll' }),
          ],
        });

        const viewMenu = await Submenu.new({
          text: t('appMenu.view'),
          items: [
            await MenuItem.new({
              id: 'fullscreen',
              text: t('appMenu.fullscreen'),
              accelerator: 'F11',
              action: async () => {
                const w = getCurrentWindow();
                const isFs = await w.isFullscreen();
                await w.setFullscreen(!isFs);
              },
            }),
            await PredefinedMenuItem.new({ item: 'Minimize', text: t('appMenu.minimize') }),
          ],
        });

        const helpMenu = await Submenu.new({
          text: t('appMenu.help'),
          items: [
            await MenuItem.new({
              id: 'docs',
              text: t('appMenu.documentation'),
              action: async () => {
                const { open } = await import('@tauri-apps/plugin-shell');
                await open('https://github.com/');
              },
            }),
            await MenuItem.new({
              id: 'about',
              text: t('appMenu.about'),
              action: () => navigate('/settings'),
            }),
          ],
        });

        installed = await Menu.new({ items: [fileMenu, editMenu, viewMenu, helpMenu] });
        await installed.setAsAppMenu();
      } catch (e) {
        console.warn('AppMenu install failed:', e);
      }
    })();

    return () => {
      // Tauri menu doesn't strictly require teardown — replaced on next mount.
      installed = null;
    };
  }, [navigate, t]);

  // Web fallback strip
  if (isTauri()) return null;
  return <WebMenuStrip />;
}

function WebMenuStrip() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState<string | null>(null);

  function close() {
    setOpen(null);
  }

  return (
    <div
      className="flex h-8 items-center gap-1 border-b border-slate-200 bg-white px-2 text-xs dark:border-slate-700 dark:bg-slate-900"
      onMouseLeave={close}
    >
      <MenuButton
        label={t('appMenu.file')}
        open={open === 'file'}
        onOpen={() => setOpen('file')}
        items={[
          { label: t('appMenu.newInspection'), onClick: () => navigate('/inspect') },
          {
            label: t('appMenu.preferences'),
            onClick: () => navigate('/settings'),
          },
        ]}
      />
      <MenuButton
        label={t('appMenu.view')}
        open={open === 'view'}
        onOpen={() => setOpen('view')}
        items={[]}
      />
      <MenuButton
        label={t('appMenu.help')}
        open={open === 'help'}
        onOpen={() => setOpen('help')}
        items={[]}
      />
    </div>
  );
}

function MenuButton({
  label,
  items,
  open,
  onOpen,
}: {
  label: string;
  open: boolean;
  onOpen: () => void;
  items: { label: string; onClick: () => void }[];
}) {
  return (
    <div className="relative">
      <button
        type="button"
        onClick={onOpen}
        className="rounded px-2 py-1 hover:bg-slate-100 dark:hover:bg-slate-700"
      >
        {label}
      </button>
      {open && items.length > 0 && (
        <div className="absolute left-0 top-full z-50 mt-0.5 min-w-[180px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800">
          {items.map((it) => (
            <button
              key={it.label}
              type="button"
              onClick={it.onClick}
              className="block w-full px-3 py-1.5 text-left text-xs hover:bg-slate-100 dark:hover:bg-slate-700"
            >
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default AppMenu;
