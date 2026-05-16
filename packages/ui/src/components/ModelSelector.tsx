import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { ChevronDown, Check, Sparkles, Cpu } from 'lucide-react';
import { cn } from '../utils/cn';

export type ModelBadge = 'pretrained' | 'custom';

export interface ModelOption {
  id: string;
  name: string;
  description?: string;
  badge?: ModelBadge;
}

interface Props {
  /** Currently selected model id */
  value: string;
  /** Fired on selection change */
  onChange: (id: string) => void;
  /** Selectable model definitions */
  options: ModelOption[];
  /** Optional disabled flag */
  disabled?: boolean;
  /** Optional extra class names for the trigger button */
  className?: string;
  /** Accessible label — defaults to "Model seçici" */
  ariaLabel?: string;
}

const BADGE_LABEL: Record<ModelBadge, string> = {
  pretrained: 'Pre-trained',
  custom: 'Kendi Modelim',
};

const BADGE_STYLE: Record<ModelBadge, string> = {
  // muted blue/gray — pretrained baseline
  pretrained: 'bg-slate-100 text-slate-700 ring-slate-300',
  // brand-green — user's own fine-tuned model
  custom: 'bg-emerald-50 text-emerald-800 ring-emerald-300',
};

/**
 * Header-friendly model selector dropdown.
 *
 * - Compact, low-chrome trigger that blends into a header bar.
 * - Custom popover (not a native <select>) so each option can show
 *   description + badge with proper visual hierarchy.
 * - Fully keyboard accessible (arrow keys / enter / esc / home / end).
 * - WCAG AA contrast on labels and badges.
 */
export function ModelSelector({
  value,
  onChange,
  options,
  disabled,
  className,
  ariaLabel = 'Model seçici',
}: Props) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState<number>(() =>
    Math.max(0, options.findIndex((o) => o.id === value)),
  );

  const listboxId = useId();
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const listRef = useRef<HTMLUListElement | null>(null);
  const itemRefs = useRef<(HTMLLIElement | null)[]>([]);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const selected = options.find((o) => o.id === value);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handlePointer(e: MouseEvent) {
      if (!rootRef.current) return;
      if (e.target instanceof Node && !rootRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handlePointer);
    return () => document.removeEventListener('mousedown', handlePointer);
  }, [open]);

  // Sync active index when opening
  useEffect(() => {
    if (open) {
      const selectedIndex = options.findIndex((o) => o.id === value);
      const next = selectedIndex >= 0 ? selectedIndex : 0;
      setActiveIndex(next);
      // focus the listbox so arrow keys work without an extra Tab
      requestAnimationFrame(() => listRef.current?.focus());
    }
  }, [open, options, value]);

  // Scroll active item into view when changed
  useEffect(() => {
    if (!open) return;
    const node = itemRefs.current[activeIndex];
    node?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex, open]);

  const commitSelection = (idx: number) => {
    const opt = options[idx];
    if (!opt) return;
    onChange(opt.id);
    setOpen(false);
    requestAnimationFrame(() => triggerRef.current?.focus());
  };

  const handleTriggerKeyDown = (e: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    if (
      e.key === 'ArrowDown' ||
      e.key === 'ArrowUp' ||
      e.key === 'Enter' ||
      e.key === ' '
    ) {
      e.preventDefault();
      setOpen(true);
    }
  };

  const handleListKeyDown = (e: ReactKeyboardEvent<HTMLUListElement>) => {
    if (!open) return;
    switch (e.key) {
      case 'ArrowDown': {
        e.preventDefault();
        setActiveIndex((i) => (i + 1) % options.length);
        break;
      }
      case 'ArrowUp': {
        e.preventDefault();
        setActiveIndex((i) => (i - 1 + options.length) % options.length);
        break;
      }
      case 'Home': {
        e.preventDefault();
        setActiveIndex(0);
        break;
      }
      case 'End': {
        e.preventDefault();
        setActiveIndex(options.length - 1);
        break;
      }
      case 'Enter':
      case ' ': {
        e.preventDefault();
        commitSelection(activeIndex);
        break;
      }
      case 'Escape':
      case 'Tab': {
        e.preventDefault();
        setOpen(false);
        requestAnimationFrame(() => triggerRef.current?.focus());
        break;
      }
    }
  };

  const triggerLabel = selected?.name ?? 'Model seç';
  const triggerBadge = selected?.badge;
  const TriggerIcon =
    triggerBadge === 'custom' ? Sparkles : triggerBadge === 'pretrained' ? Cpu : Cpu;

  return (
    <div ref={rootRef} className={cn('relative inline-block text-left', className)}>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        aria-label={ariaLabel}
        onClick={() => !disabled && setOpen((o) => !o)}
        onKeyDown={handleTriggerKeyDown}
        className={cn(
          'inline-flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white/80 px-2.5 text-sm font-medium text-slate-800',
          'shadow-sm backdrop-blur transition-colors',
          'hover:bg-white hover:border-slate-300',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1',
          'disabled:cursor-not-allowed disabled:opacity-60',
        )}
      >
        <TriggerIcon className="h-4 w-4 flex-none text-slate-500" aria-hidden />
        <span className="max-w-[10rem] truncate">{triggerLabel}</span>
        {triggerBadge && (
          <span
            className={cn(
              'hidden sm:inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ring-inset',
              BADGE_STYLE[triggerBadge],
            )}
          >
            {BADGE_LABEL[triggerBadge]}
          </span>
        )}
        <ChevronDown
          className={cn(
            'h-4 w-4 flex-none text-slate-400 transition-transform',
            open && 'rotate-180',
          )}
          aria-hidden
        />
      </button>

      {open && (
        <ul
          ref={listRef}
          id={listboxId}
          role="listbox"
          tabIndex={-1}
          aria-activedescendant={`${listboxId}-opt-${activeIndex}`}
          aria-label={ariaLabel}
          onKeyDown={handleListKeyDown}
          className={cn(
            'absolute right-0 z-50 mt-2 max-h-80 w-80 overflow-auto rounded-lg border border-slate-200 bg-white p-1 shadow-lg',
            'animate-fade-in focus:outline-none',
          )}
        >
          {options.map((opt, idx) => {
            const isSelected = opt.id === value;
            const isActive = idx === activeIndex;
            return (
              <li
                key={opt.id}
                ref={(el) => {
                  itemRefs.current[idx] = el;
                }}
                id={`${listboxId}-opt-${idx}`}
                role="option"
                aria-selected={isSelected}
                onMouseEnter={() => setActiveIndex(idx)}
                onClick={() => commitSelection(idx)}
                className={cn(
                  'flex cursor-pointer items-start gap-2.5 rounded-md px-2.5 py-2',
                  isActive ? 'bg-brand-50' : 'bg-transparent',
                )}
              >
                <span
                  className={cn(
                    'mt-0.5 flex h-4 w-4 flex-none items-center justify-center',
                    isSelected ? 'text-brand-600' : 'text-transparent',
                  )}
                  aria-hidden
                >
                  <Check className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={cn(
                        'text-sm font-medium text-slate-900',
                        isSelected && 'text-brand-800',
                      )}
                    >
                      {opt.name}
                    </span>
                    {opt.badge && (
                      <span
                        className={cn(
                          'inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ring-inset',
                          BADGE_STYLE[opt.badge],
                        )}
                      >
                        {BADGE_LABEL[opt.badge]}
                      </span>
                    )}
                  </div>
                  {opt.description && (
                    <p className="mt-0.5 text-xs leading-snug text-slate-500">
                      {opt.description}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
