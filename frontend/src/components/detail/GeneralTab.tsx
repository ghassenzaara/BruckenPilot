import { useEffect, useRef, useState } from 'react';
import { Building2, Activity, Gauge, TrendingUp, Sparkles, Info } from 'lucide-react';
import {
  Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid, Legend,
} from 'recharts';
import type { Bridge, Pruefung } from '@/types';
import { getUrgency } from '@/lib/urgency';
import { cn } from '@/lib/utils';
import { Widget, Stat } from './Widget';

type SvdKey = 's' | 'v' | 'd';

function noteColor(n?: number) {
  if (n == null) return '#94a3b8';
  return n < 2 ? '#22c55e' : n < 3 ? '#eab308' : n < 3.5 ? '#f97316' : '#ef4444';
}

export function GeneralTab({ bridge, pruefungen }: { bridge: Bridge; pruefungen: Pruefung[] }) {
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [openSvd, setOpenSvd] = useState<SvdKey | null>(null);
  const svdRef = useRef<HTMLDivElement>(null);
  const urgency = getUrgency(bridge);
  const eur = (n?: number) =>
    n == null ? '—' : new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(n);

  // Close the S/V/D explanation popover when the user clicks anywhere outside
  // the boxes (and on Escape) — standard popover dismissal.
  useEffect(() => {
    if (!openSvd) return;
    const onDown = (e: MouseEvent) => {
      if (svdRef.current && !svdRef.current.contains(e.target as Node)) setOpenSvd(null);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpenSvd(null); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [openSvd]);

  const svdValue = (k: SvdKey) =>
    k === 's' ? bridge.max_s : k === 'v' ? bridge.max_v : bridge.max_d;
  const svdExplanation = (k: SvdKey) =>
    k === 's' ? bridge.max_s_begruendung
      : k === 'v' ? bridge.max_v_begruendung
      : bridge.max_d_begruendung;

  // only points that actually have a Zustandsnote — keeps the line continuous
  const history = pruefungen
    .filter((p) => p.datum && p.zustandsnote != null)
    .sort((a, b) => a.datum.localeCompare(b.datum))
    .map((p) => ({
      datum: p.datum,
      Zustand: p.zustandsnote,
    }));

  return (
    <div className="space-y-4">
      {/* condition headline — relative z-30 so the S/V/D popover paints ABOVE the
          Priorität widget below it (each widget is its own stacking context via
          the animate-in-up transform, so the popover must be lifted explicitly) */}
      <Widget title="Zustand" icon={<Activity className="h-4 w-4" />} className="relative z-30 p-5">
        <div className="flex items-end gap-6">
          <div>
            <p className="text-5xl font-extrabold tabular-nums" style={{ color: noteColor(bridge.aktuelle_zustandsnote) }}>
              {bridge.aktuelle_zustandsnote?.toFixed(1) ?? '—'}
            </p>
            <p className="text-sm font-medium text-muted-foreground">Zustandsnote</p>
          </div>
          <div ref={svdRef} className="relative ml-auto">
            <div className="flex gap-1.5">
              {(['s', 'v', 'd'] as const).map((k) => {
                const v = svdValue(k);
                const active = openSvd === k;
                return (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setOpenSvd(active ? null : k)}
                    aria-expanded={active}
                    aria-label={`Begründung ${k.toUpperCase()} anzeigen`}
                    className={cn(
                      'grid h-14 w-14 place-items-center rounded-xl border bg-background/60 transition-colors',
                      'hover:border-primary hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-primary',
                      active && 'border-primary ring-2 ring-primary/30',
                    )}
                  >
                    <span className="text-xs font-medium text-muted-foreground">{k.toUpperCase()}</span>
                    <span className="text-lg font-extrabold tabular-nums">{v ?? '–'}</span>
                  </button>
                );
              })}
            </div>
            {openSvd && (
              <div
                role="dialog"
                className="absolute right-0 top-full z-30 mt-2 w-80 rounded-2xl border-2 border-border bg-popover p-4 text-popover-foreground shadow-2xl ring-1 ring-black/10"
              >
                <p className="mb-2 flex items-center gap-1.5 text-sm font-bold uppercase tracking-wide text-primary">
                  <Info className="h-4 w-4" /> Begründung {openSvd.toUpperCase()} = {svdValue(openSvd) ?? '–'}
                </p>
                <p className="text-[15px] font-medium leading-relaxed text-foreground">
                  {svdExplanation(openSvd) || 'Keine Begründung im Dokument vorhanden.'}
                </p>
              </div>
            )}
          </div>
        </div>
      </Widget>

      {/* priority */}
      <Widget title="Priorität" icon={<Gauge className="h-4 w-4" />}>
        <div className="mb-4 flex items-center gap-4">
          <div
            className="flex h-[4.5rem] w-[4.5rem] flex-col items-center justify-center rounded-2xl leading-none text-white shadow-lg"
            style={{ background: urgency.color }}
          >
            <span className="text-2xl font-extrabold">{Math.round((bridge.priority_score ?? 0) * 100)}</span>
            <span className="mt-0.5 text-[10px] font-semibold opacity-80">/ 100</span>
          </div>
          <div>
            <p className="text-lg font-bold">{urgency.label}</p>
            <p className="text-sm text-muted-foreground">Geschätzte Kosten</p>
            <p className="text-lg font-extrabold tabular-nums grad-text">{eur(bridge.geschaetzte_kosten_eur)}</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 border-t pt-3">
          <div>
            <p className="text-xs font-medium text-muted-foreground">Verkehr (DTV)</p>
            <p className="text-base font-bold tabular-nums">
              {bridge.dtv_gesamt != null ? `${bridge.dtv_gesamt.toLocaleString('de-DE')} Kfz/Tag` : '—'}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">Straßenklasse</p>
            <p className="text-base font-bold">{bridge.strassenklasse ?? '—'}</p>
          </div>
        </div>
      </Widget>

      {/* history */}
      {history.length > 1 && (
        <Widget title="Verlauf der Prüfungen" icon={<TrendingUp className="h-4 w-4" />}>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={history} margin={{ top: 6, right: 8, left: -22, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                <XAxis
                  dataKey="datum"
                  tickFormatter={(d) => String(d).slice(0, 4)}
                  tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis domain={[1, 4]} ticks={[1, 2, 3, 4]} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} tickLine={false} axisLine={false} />
                <Tooltip
                  labelFormatter={(d) => String(d)}
                  contentStyle={{
                    background: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))',
                    borderRadius: 12, fontSize: 12, color: 'hsl(var(--foreground))',
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="Zustand" stroke="#ef4444" strokeWidth={2.5} dot={{ r: 3 }} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Widget>
      )}

      {/* stammdaten */}
      <Widget title="Stammdaten" icon={<Building2 className="h-4 w-4" />}>
        <div className="space-y-3">
          <Stat label="Ort" value={bridge.ort} />
          <Stat label="Straße" value={[bridge.strasse, bridge.strassenklasse].filter(Boolean).join(' · ')} />
          <Stat label="Baujahr" value={bridge.baujahr_ueberbau} />
          <Stat label="Baustoff" value={bridge.hauptbaustoff} />
          <Stat label="Konstruktion" value={bridge.konstruktion} />
          <Stat label="Bauwerksart" value={bridge.bauwerksart} />
          <Stat label="Länge" value={bridge.laenge_m ? `${bridge.laenge_m} m` : undefined} />
          <Stat label="Fläche" value={bridge.brueckenflaeche_m2 ? `${bridge.brueckenflaeche_m2} m²` : undefined} />
          <Stat label="DTV" value={bridge.dtv_gesamt?.toLocaleString('de-DE')} />
          <Stat label="LKW-Anteil" value={bridge.lkw_anteil_pct ? `${bridge.lkw_anteil_pct} %` : undefined} />
          <Stat label="Baulast" value={bridge.baulast} />
          <Stat label="Amt" value={bridge.amt} />
        </div>
      </Widget>

      {/* intelligent summary — collapsible, clamped by default */}
      {bridge.intelligent_summary && (
        <Widget
          title="KI-Einschätzung"
          icon={<Sparkles className="h-4 w-4" />}
          action={
            <button onClick={() => setSummaryOpen((o) => !o)} className="text-xs font-medium text-primary hover:underline">
              {summaryOpen ? 'Weniger' : 'Mehr'}
            </button>
          }
        >
          <div className="space-y-3 text-sm">
            {([
              ['Situation', bridge.intelligent_summary.situation],
              ['Risiken', bridge.intelligent_summary.risiken],
              ['Empfehlung', bridge.intelligent_summary.empfehlung],
            ] as const).map(([label, text]) => (
              <div key={label}>
                <p className="mb-0.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-primary">
                  <Info className="h-3 w-3" /> {label}
                </p>
                <p className={cn('leading-relaxed text-muted-foreground', !summaryOpen && 'line-clamp-2')}>{text}</p>
              </div>
            ))}
          </div>
        </Widget>
      )}
    </div>
  );
}
