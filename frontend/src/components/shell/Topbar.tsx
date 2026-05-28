import { useMemo, useRef, useState, useEffect } from 'react';
import { Search, Sun, Moon, MapPin } from 'lucide-react';
import { useTheme } from '@/lib/theme';
import { getUrgency } from '@/lib/urgency';
import type { Bridge } from '@/types';
import type { View } from './Sidebar';

interface TopbarProps {
  view: View;
  search: string;
  setSearch: (s: string) => void;
  bridges: Bridge[];
  onSelect: (b: Bridge) => void;
}

const TITLES: Record<View, string> = { map: 'Karte', list: 'Alle Brücken' };

export function Topbar({ view, search, setSearch, bridges, onSelect }: TopbarProps) {
  const { resolved, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  // matches by name / Bauwerksnummer / Ort — capped so the dropdown stays light
  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return [];
    return bridges
      .filter((b) => [b.name, b.bauwerksnummer, b.ort, b.strasse]
        .filter(Boolean).some((s) => s!.toLowerCase().includes(q)))
      .slice(0, 8);
  }, [bridges, search]);

  // close the dropdown on any outside click
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, []);

  const pick = (b: Bridge) => {
    onSelect(b);
    setSearch('');
    setOpen(false);
  };

  return (
    <header className="flex h-16 shrink-0 items-center gap-4 border-b bg-card/40 px-6">
      <div>
        <h1 className="text-lg font-bold leading-none tracking-tight">{TITLES[view]}</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">{bridges.length} Bauwerke im Bestand</p>
      </div>

      <div ref={boxRef} className="relative ml-4 max-w-md flex-1">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && matches.length) pick(matches[0]);
            if (e.key === 'Escape') setOpen(false);
          }}
          placeholder="Brücke, Bauwerksnummer oder Ort suchen…"
          className="h-10 w-full rounded-xl border bg-background/60 pl-10 pr-4 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/20"
        />

        {open && search.trim() && (
          <div className="absolute left-0 right-0 top-full z-40 mt-2 overflow-hidden rounded-xl border bg-popover text-popover-foreground shadow-2xl ring-1 ring-black/10">
            {matches.length === 0 ? (
              <p className="px-4 py-3 text-sm text-muted-foreground">Keine Treffer.</p>
            ) : (
              matches.map((b) => {
                const u = getUrgency(b);
                return (
                  <button
                    key={b.id}
                    onClick={() => pick(b)}
                    className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-accent"
                  >
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: u.color }} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold">{b.name || 'Unbenanntes Bauwerk'}</span>
                      <span className="block truncate text-xs text-muted-foreground">
                        Nr. {b.bauwerksnummer}{b.ort ? ` · ${b.ort}` : ''}
                      </span>
                    </span>
                    <MapPin className="h-4 w-4 shrink-0 text-muted-foreground" />
                  </button>
                );
              })
            )}
          </div>
        )}
      </div>

      <div className="ml-auto flex items-center gap-2">
        <button
          onClick={() => setTheme(resolved === 'dark' ? 'light' : 'dark')}
          className="grid h-10 w-10 place-items-center rounded-xl border bg-background/60 text-muted-foreground transition-colors hover:text-foreground"
          title="Theme wechseln"
        >
          {resolved === 'dark' ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
        </button>
      </div>
    </header>
  );
}
