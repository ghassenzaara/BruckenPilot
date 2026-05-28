import { Map as MapIcon, LayoutGrid, Waypoints } from 'lucide-react';
import type { Bridge } from '@/types';
import { getUrgency, URGENCY_LEVELS, urgencyMeta, type UrgencyLevel } from '@/lib/urgency';
import { cn } from '@/lib/utils';
import { AccountMenu } from './AccountMenu';

export type View = 'map' | 'list';

interface SidebarProps {
  view: View;
  setView: (v: View) => void;
  bridges: Bridge[];
  activeUrgencies: Set<UrgencyLevel>;
  toggleUrgency: (l: UrgencyLevel) => void;
}

export function Sidebar({ view, setView, bridges, activeUrgencies, toggleUrgency }: SidebarProps) {
  const counts = bridges.reduce<Record<string, number>>((acc, b) => {
    const lvl = getUrgency(b).level;
    acc[lvl] = (acc[lvl] ?? 0) + 1;
    return acc;
  }, {});

  const nav: { id: View; label: string; icon: typeof MapIcon }[] = [
    { id: 'map', label: 'Karte', icon: MapIcon },
    { id: 'list', label: 'Alle Brücken', icon: LayoutGrid },
  ];

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r bg-card/40 p-4">
      {/* logo */}
      <div className="mb-7 flex items-center gap-2.5 px-2">
        <div className="grad-bg grid h-9 w-9 place-items-center rounded-xl text-white shadow-lg">
          <Waypoints className="h-5 w-5" />
        </div>
        <div className="leading-tight">
          <p className="text-base font-extrabold tracking-tight">Brücken<span className="grad-text">Pilot</span></p>
          <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Bauwerksmonitor</p>
        </div>
      </div>

      {/* nav */}
      <nav className="space-y-1">
        {nav.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setView(id)}
            className={cn(
              'flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all',
              view === id
                ? 'grad-bg text-white shadow-md'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground',
            )}
          >
            <Icon className="h-[18px] w-[18px]" />
            {label}
          </button>
        ))}
      </nav>

      {/* urgency filter */}
      <div className="mt-7">
        <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Dringlichkeit
        </p>
        <div className="space-y-1">
          {URGENCY_LEVELS.map((lvl) => {
            const active = activeUrgencies.has(lvl);
            const { label, color } = urgencyMeta(lvl);
            return (
              <button
                key={lvl}
                onClick={() => toggleUrgency(lvl)}
                className={cn(
                  'flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-all',
                  active ? 'bg-accent text-foreground' : 'text-muted-foreground opacity-50 hover:opacity-100',
                )}
              >
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: color, boxShadow: active ? `0 0 8px ${color}` : 'none' }}
                />
                <span className="flex-1 text-left">{label}</span>
                <span className="text-xs font-semibold tabular-nums text-muted-foreground">{counts[lvl] ?? 0}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1" />

      {/* Konto */}
      <div className="border-t pt-3">
        <AccountMenu />
      </div>
    </aside>
  );
}
