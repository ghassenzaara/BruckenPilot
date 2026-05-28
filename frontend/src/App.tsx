import { useMemo, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AnimatePresence } from 'framer-motion';
import { Sidebar, type View } from './components/shell/Sidebar';
import { Topbar } from './components/shell/Topbar';
import { GermanyMap } from './components/Map/GermanyMap';
import { AllBridges } from './components/AllBridges';
import { BridgePanel } from './components/detail/BridgePanel';
import { useBridges } from './hooks/useSupabase';
import { getUrgency, URGENCY_LEVELS, type UrgencyLevel } from './lib/urgency';
import type { Bridge, Contractor } from './types';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, retryDelay: 500, staleTime: 60_000 } },
});

function Dashboard() {
  const { data: bridges = [], isError, error } = useBridges();
  const [view, setView] = useState<View>('map');
  const [selected, setSelected] = useState<Bridge | null>(null);
  const [pinnedContractor, setPinnedContractor] = useState<Contractor | null>(null);
  const [search, setSearch] = useState('');

  // switching/closing a bridge clears any contractor pin
  const selectBridge = (b: Bridge | null) => { setSelected(b); setPinnedContractor(null); };
  const togglePin = (c: Contractor) =>
    setPinnedContractor((p) => (p?.id === c.id ? null : c));
  const [activeUrgencies, setActiveUrgencies] = useState<Set<UrgencyLevel>>(new Set(URGENCY_LEVELS));

  const toggleUrgency = (l: UrgencyLevel) =>
    setActiveUrgencies((prev) => {
      const next = new Set(prev);
      next.has(l) ? next.delete(l) : next.add(l);
      return next.size === 0 ? new Set(URGENCY_LEVELS) : next; // never empty
    });

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return bridges.filter((b) => {
      if (!activeUrgencies.has(getUrgency(b).level)) return false;
      if (!q) return true;
      return [b.name, b.bauwerksnummer, b.ort, b.strasse]
        .filter(Boolean)
        .some((s) => s!.toLowerCase().includes(q));
    });
  }, [bridges, activeUrgencies, search]);

  const selectFromList = (b: Bridge) => {
    setView('map');
    selectBridge(b);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <Sidebar
        view={view}
        setView={setView}
        bridges={bridges}
        activeUrgencies={activeUrgencies}
        toggleUrgency={toggleUrgency}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <Topbar view={view} search={search} setSearch={setSearch} bridges={bridges} onSelect={selectFromList} />

        <div className="relative min-h-0 flex-1">
          {isError && (
            <div className="absolute left-1/2 top-4 z-30 -translate-x-1/2 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
              Supabase-Fehler: {(error as Error)?.message}
            </div>
          )}

          {view === 'map' ? (
            <GermanyMap
              bridges={filtered}
              selectedId={selected?.id}
              onSelect={selectBridge}
              contractor={pinnedContractor}
            />
          ) : (
            <AllBridges bridges={filtered} onSelect={selectFromList} />
          )}

          <AnimatePresence>
            {view === 'map' && selected && (
              <BridgePanel
                key={selected.id}
                bridge={selected}
                onClose={() => selectBridge(null)}
                pinnedContractorId={pinnedContractor?.id}
                onPinContractor={togglePin}
              />
            )}
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Dashboard />
    </QueryClientProvider>
  );
}
