import { useEffect, useRef, useState } from 'react';
import { User, Settings, LogOut, Sun, Moon, Monitor, ChevronDown } from 'lucide-react';
import { useTheme, type Theme } from '@/lib/theme';
import { cn } from '@/lib/utils';

const THEMES: { value: Theme; icon: typeof Sun; label: string }[] = [
  { value: 'light', icon: Sun, label: 'Hell' },
  { value: 'dark', icon: Moon, label: 'Dunkel' },
  { value: 'system', icon: Monitor, label: 'System' },
];

export function AccountMenu({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'flex items-center gap-3 rounded-xl p-2 transition-colors hover:bg-accent w-full',
          compact && 'p-1.5',
        )}
      >
        <div className="grad-bg grid h-9 w-9 shrink-0 place-items-center rounded-lg text-sm font-bold text-white">
          BP
        </div>
        {!compact && (
          <div className="min-w-0 flex-1 text-left">
            <p className="truncate text-sm font-semibold">BrückenPilot Admin</p>
            <p className="truncate text-xs text-muted-foreground">admin@brueckenpilot.de</p>
          </div>
        )}
        <ChevronDown className={cn('h-4 w-4 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="absolute bottom-full left-0 z-50 mb-2 w-64 origin-bottom animate-in-up rounded-2xl border bg-popover p-2 shadow-2xl">
          <div className="flex items-center gap-3 rounded-xl px-2 py-2">
            <div className="grad-bg grid h-10 w-10 place-items-center rounded-lg text-sm font-bold text-white">BP</div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">BrückenPilot Admin</p>
              <p className="truncate text-xs text-muted-foreground">admin@brueckenpilot.de</p>
            </div>
          </div>

          <div className="my-2 px-2">
            <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Theme</p>
            <div className="grid grid-cols-3 gap-1 rounded-lg bg-muted p-1">
              {THEMES.map(({ value, icon: Icon, label }) => (
                <button
                  key={value}
                  onClick={() => setTheme(value)}
                  className={cn(
                    'flex flex-col items-center gap-1 rounded-md py-1.5 text-[11px] transition-colors',
                    theme === value ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="my-1 h-px bg-border" />
          {[
            { icon: User, label: 'Profil' },
            { icon: Settings, label: 'Einstellungen' },
            { icon: LogOut, label: 'Abmelden' },
          ].map(({ icon: Icon, label }) => (
            <button
              key={label}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
