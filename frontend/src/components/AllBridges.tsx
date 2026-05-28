import { MapPin, ArrowUpRight } from 'lucide-react';
import type { Bridge } from '@/types';
import { getUrgency } from '@/lib/urgency';

function noteColor(n?: number) {
  if (n == null) return '#94a3b8';
  return n < 2 ? '#22c55e' : n < 3 ? '#eab308' : n < 3.5 ? '#f97316' : '#ef4444';
}

export function AllBridges({ bridges, onSelect }: { bridges: Bridge[]; onSelect: (b: Bridge) => void }) {
  const sorted = [...bridges].sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0));

  if (!sorted.length) {
    return (
      <div className="grid h-full place-items-center text-sm text-muted-foreground">
        Keine Brücken entsprechen den Filtern.
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {sorted.map((b) => {
          const u = getUrgency(b);
          return (
            <button
              key={b.id}
              onClick={() => onSelect(b)}
              className="group animate-in-up overflow-hidden rounded-2xl border bg-card/60 p-0 text-left transition-all hover:-translate-y-0.5 hover:shadow-xl hover:shadow-primary/5"
            >
              <div className="h-1.5 w-full" style={{ background: u.color }} />
              <div className="p-4">
                <div className="mb-2 flex items-center justify-between">
                  <span
                    className="rounded-full px-2 py-0.5 text-[11px] font-bold text-white"
                    style={{ background: u.color }}
                  >
                    {u.label}
                  </span>
                  <ArrowUpRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                </div>
                <h3 className="truncate font-semibold leading-tight">{b.name || 'Unbenannt'}</h3>
                <p className="flex items-center gap-1 text-xs text-muted-foreground">
                  <MapPin className="h-3 w-3" /> {b.ort || '—'} · Nr. {b.bauwerksnummer}
                </p>

                <div className="mt-3 flex items-end justify-between">
                  <div>
                    <p className="text-2xl font-extrabold tabular-nums" style={{ color: noteColor(b.aktuelle_zustandsnote) }}>
                      {b.aktuelle_zustandsnote?.toFixed(1) ?? '—'}
                    </p>
                    <p className="text-[11px] text-muted-foreground">Zustandsnote</p>
                  </div>
                  <div className="text-right">
                    <p className="grad-text text-2xl font-extrabold tabular-nums">
                      {Math.round((b.priority_score ?? 0) * 100)}
                    </p>
                    <p className="text-[11px] text-muted-foreground">Priorität</p>
                  </div>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
