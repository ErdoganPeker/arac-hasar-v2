/**
 * App shell.
 *
 * Layout:
 *   ┌─────────────────────────────────────────┐
 *   │ AppMenu (Tauri native menubar)          │
 *   ├──────────┬──────────────────────────────┤
 *   │ Sidebar  │ TopBar (user, lang, theme)   │
 *   │  (nav)   ├──────────────────────────────┤
 *   │          │ Routes outlet                │
 *   └──────────┴──────────────────────────────┘
 *
 * Routes:
 *   /login       (public)
 *   /register    (public)
 *   /            DashboardPage         (protected)
 *   /inspect     InspectPage           (protected)
 *   /batch       BatchPage             (protected)
 *   /inspections InspectionsPage       (protected)
 *   /inspection/:id  InspectionDetail  (protected)
 *   /results/:id  → redirect to /inspection/:id (back-compat)
 *   /settings    SettingsPage          (protected)
 *
 * Also installs: AppMenu (native), SystemTray, KeyboardShortcuts, file drop relay.
 */
import { useEffect, useState } from 'react';
import { Navigate, Route, Routes, NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity,
  ChevronLeft,
  ChevronRight,
  FolderOpen,
  Home,
  ListChecks,
  LogOut,
  Settings,
  Upload,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/contexts/AuthContext';
import { loadSettings, saveSetting } from '@/lib/settings';
import { useTheme } from '@/contexts/ThemeContext';
import LoginPage from '@/pages/LoginPage';
import RegisterPage from '@/pages/RegisterPage';
import DashboardPage from '@/pages/DashboardPage';
import InspectPage from '@/pages/InspectPage';
import BatchPage from '@/pages/BatchPage';
import InspectionsPage from '@/pages/InspectionsPage';
import InspectionDetailPage from '@/pages/InspectionDetailPage';
import SettingsPage from '@/pages/SettingsPage';
import ProtectedRoute from '@/components/ProtectedRoute';
import AppMenu from '@/components/AppMenu';
import SystemTray from '@/components/SystemTray';
import KeyboardShortcuts from '@/components/KeyboardShortcuts';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import ThemeToggle from '@/components/ThemeToggle';
import WindowFileDrop from '@/components/WindowFileDrop';
import Toaster from '@/components/Toaster';

export default function App() {
  const { ready } = useAuth();
  const { mode: themeMode } = useTheme();
  // theme provider already applies the dark class — read once just to ensure the hook subscribes
  void themeMode;

  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-50 dark:bg-slate-950">
        <div className="text-sm text-slate-500">Hasarİ…</div>
      </div>
    );
  }

  return (
    <>
      <KeyboardShortcuts />
      <SystemTray />
      <WindowFileDrop />
      <Toaster />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/results/:id" element={<RedirectToInspection />} />
        <Route
          path="*"
          element={
            <ProtectedRoute>
              <Shell />
            </ProtectedRoute>
          }
        />
      </Routes>
    </>
  );
}

function RedirectToInspection() {
  const loc = useLocation();
  const id = loc.pathname.split('/').pop();
  return <Navigate to={`/inspection/${id}`} replace />;
}

function Shell() {
  return (
    <div className="flex h-screen flex-col bg-slate-50 dark:bg-slate-950">
      <AppMenu />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <div className="flex flex-1 flex-col">
          <TopBar />
          <main className="flex-1 overflow-y-auto p-6">
            <Routes>
              <Route index element={<DashboardPage />} />
              <Route path="inspect" element={<InspectPage />} />
              <Route path="batch" element={<BatchPage />} />
              <Route path="inspections" element={<InspectionsPage />} />
              <Route path="inspection/:id" element={<InspectionDetailPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </div>
  );
}

interface NavItem {
  to: string;
  icon: typeof Home;
  key: 'dashboard' | 'newInspection' | 'batch' | 'inspections' | 'settings';
  end?: boolean;
}

const NAV_ITEMS: readonly NavItem[] = [
  { to: '/', icon: Home, key: 'dashboard', end: true },
  { to: '/inspect', icon: Upload, key: 'newInspection' },
  { to: '/batch', icon: FolderOpen, key: 'batch' },
  { to: '/inspections', icon: ListChecks, key: 'inspections' },
  { to: '/settings', icon: Settings, key: 'settings' },
];

function Sidebar() {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    loadSettings().then((s) => setCollapsed(s.sidebarCollapsed));
  }, []);

  function toggle() {
    setCollapsed((c) => {
      saveSetting('sidebarCollapsed', !c);
      return !c;
    });
  }

  return (
    <aside
      className={`relative flex flex-col border-r border-slate-200 bg-white transition-[width] duration-200 dark:border-slate-700 dark:bg-slate-900 ${
        collapsed ? 'w-14' : 'w-56'
      }`}
    >
      <div className="flex h-12 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-700">
        {!collapsed && (
          <div className="flex items-center gap-1.5">
            <Activity className="h-5 w-5 text-brand-600" />
            <span className="font-bold text-slate-800 dark:text-white">Hasarİ</span>
          </div>
        )}
        <button
          type="button"
          onClick={toggle}
          className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-white"
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 p-2">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-brand-100 text-brand-800 dark:bg-brand-900/30 dark:text-brand-200'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white'
              } ${collapsed ? 'justify-center' : ''}`
            }
            title={collapsed ? t(`nav.${item.key}`) : undefined}
          >
            <item.icon className="h-4 w-4 shrink-0" />
            {!collapsed && <span className="truncate">{t(`nav.${item.key}`)}</span>}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}

function TopBar() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const loc = useLocation();
  const item = NAV_ITEMS.find((n) =>
    n.end ? loc.pathname === n.to : loc.pathname.startsWith(n.to),
  );
  return (
    <div className="titlebar-drag flex h-12 items-center justify-between border-b border-slate-200 bg-white px-4 dark:border-slate-700 dark:bg-slate-900">
      <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">
        {item ? t(`nav.${item.key}`) : ''}
      </div>
      <div className="titlebar-button flex items-center gap-2">
        <LanguageSwitcher compact />
        <ThemeToggle />
        {user && (
          <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-800">
            <div className="text-slate-700 dark:text-slate-200" title={user.email}>
              {user.full_name}
            </div>
            <button
              type="button"
              onClick={async () => {
                await logout();
                navigate('/login', { replace: true });
              }}
              className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-white"
              title={t('nav.logout')}
            >
              <LogOut className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
