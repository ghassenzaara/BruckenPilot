import { useMemo, useState } from 'react';
import { MapPin, Phone, Mail, Wrench, ExternalLink, Crosshair } from 'lucide-react';
import type { Bridge, Contractor } from '@/types';
import { haversineKm } from '@/lib/geo';

/** Google Maps deep-link to a contractor's exact coordinates. */
const gmapsUrl = (c: Contractor) =>
  `https://www.google.com/maps/search/?api=1&query=${c.lat},${c.lon}`;

const LB_LABELS: Record<string, string> = {
  '613_01': 'Komplettleistungen Brückenbau',
  '311_03': 'Spannbetonarbeiten',
  '311_06': 'Stahlverbundarbeiten',
  '311_07': 'Stahlbauarbeiten',
  '311_10': 'Korrosionsschutzarbeiten Ingenieurbau',
  '311_11': 'Betonerhaltungsarbeiten',
  '311_12': 'Abdichtungsarbeiten Ingenieurbau',
};

function LbTag({ code, highlight = false }: { code: string; highlight?: boolean }) {
  const label = LB_LABELS[code] ?? code;
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold ${
        highlight
          ? 'bg-primary/15 text-primary'
          : 'bg-accent text-accent-foreground'
      }`}
    >
      {label}
    </span>
  );
}

export function ContractorsTab({
  bridge, contractors, pinnedId, onPin,
}: {
  bridge: Bridge;
  contractors: Contractor[];
  pinnedId?: string;
  onPin?: (c: Contractor) => void;
}) {
  const [radius, setRadius] = useState(50);
  const required = bridge.benoetigte_leistungsbereiche ?? [];

  const matches = useMemo(() => {
    return contractors
      .filter((c) => c.lat != null && c.lon != null)
      .map((c) => {
        const km = haversineKm(bridge.lat, bridge.lon, c.lat, c.lon);
        const overlap = (c.leistungsbereiche ?? []).filter((lb) => required.includes(lb));
        return { c, km, overlap };
      })
      .filter((m) => m.overlap.length > 0 && m.km <= radius)
      .sort((a, b) => a.km - b.km);
  }, [contractors, bridge, required, radius]);

  return (
    <div className="space-y-3">
      {/* Umkreis control */}
      <div className="rounded-2xl border bg-card/60 p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-semibold">Umkreis</span>
          <span className="grad-text text-sm font-bold tabular-nums">{radius} km</span>
        </div>
        <input
          type="range" min={5} max={200} step={5} value={radius}
          onChange={(e) => setRadius(Number(e.target.value))}
          className="w-full accent-[hsl(var(--primary))]"
        />
        <p className="mt-2 text-xs text-muted-foreground">
          {matches.length} passende Firmen · gefiltert nach Entfernung & Leistungsbereich
        </p>
      </div>

      {required.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {required.map((lb) => <LbTag key={lb} code={lb} />)}
        </div>
      )}

      {matches.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          Keine Firmen im {radius}-km-Umkreis mit passender Qualifikation.
        </p>
      ) : (
        matches.map(({ c, km, overlap }) => (
          <div key={c.id} className="animate-in-up rounded-2xl border bg-card/60 p-3.5">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{c.firmenname}</p>
                <p className="flex items-center gap-1 text-xs text-muted-foreground">
                  <MapPin className="h-3 w-3" /> {c.ort}
                </p>
              </div>
              <span className="shrink-0 rounded-lg grad-bg px-2 py-1 text-xs font-bold text-white">
                {km.toFixed(1)} km
              </span>
            </div>
            <div className="mt-2 flex items-center gap-1.5">
              <Wrench className="h-3 w-3 text-muted-foreground" />
              <div className="flex flex-wrap gap-1">
                {overlap.map((lb) => <LbTag key={lb} code={lb} highlight />)}
              </div>
            </div>
            {(c.telefon || c.email) && (
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                {c.telefon && <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{c.telefon}</span>}
                {c.email && <span className="flex items-center gap-1 truncate"><Mail className="h-3 w-3" />{c.email}</span>}
              </div>
            )}

            {/* location actions */}
            <div className="mt-3 flex items-center gap-2">
              <button
                onClick={() => onPin?.(c)}
                className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                  pinnedId === c.id
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'bg-background/60 text-muted-foreground hover:bg-accent hover:text-foreground'
                }`}
              >
                <Crosshair className="h-3.5 w-3.5" />
                {pinnedId === c.id ? 'Auf Karte ✓' : 'Auf Karte zeigen'}
              </button>
              <a
                href={gmapsUrl(c)}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 rounded-lg border bg-background/60 px-2.5 py-1.5 text-xs font-semibold text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Google Maps
              </a>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
