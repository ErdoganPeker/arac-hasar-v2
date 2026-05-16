/**
 * ThemeToggle — cycles light → dark → system. Icon reflects the *effective* state.
 */
import { Moon, Sun, MonitorSmartphone } from 'lucide-react';
import { useTheme } from '@/contexts/ThemeContext';

export function ThemeToggle() {
  const { mode, toggle } = useTheme();
  const Icon = mode === 'light' ? Sun : mode === 'dark' ? Moon : MonitorSmartphone;
  return (
    <button
      type="button"
      onClick={toggle}
      title={`Tema: ${mode}`}
      className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
    >
      <Icon className="h-4 w-4" />
    </button>
  );
}

export default ThemeToggle;
