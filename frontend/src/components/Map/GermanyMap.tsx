import { useEffect, useMemo, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import germanyStates from '@/assets/germany-states.json';
import type { Bridge, Contractor } from '@/types';
import { getUrgency, URGENCY_LEVELS, urgencyMeta } from '@/lib/urgency';
import { pointInGeometry } from '@/lib/geo';
import { useTheme } from '@/lib/theme';

const MAX_BOUNDS: [[number, number], [number, number]] = [[1, 44], [20, 58]];
const FIT_BOUNDS: [[number, number], [number, number]] = [[4.8, 46.4], [15.9, 55.8]];
const PADDING = 70;
const RANK = ['niedrig', 'mittel', 'hoch', 'kritisch'];

function cssVar(name: string) {
  return `hsl(${getComputedStyle(document.documentElement).getPropertyValue(name).trim()})`;
}

const fillExpr = (base: string): any =>
  ['case', ['to-boolean', ['get', 'urgencyColor']], ['get', 'urgencyColor'], base];

interface Props {
  bridges: Bridge[];
  selectedId?: string;
  onSelect: (b: Bridge) => void;
  contractor?: Contractor | null;
}

export function GermanyMap({ bridges, selectedId, onSelect, contractor }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const contractorMarkerRef = useRef<maplibregl.Marker | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { resolved } = useTheme();

  // Tint each Bundesland by the worst urgency of bridges located inside it.
  const tintedGeo = useMemo(() => {
    const fc = structuredClone(germanyStates) as any;
    for (const f of fc.features) {
      let worst = -1;
      let color: string | null = null;
      for (const b of bridges) {
        if (b.lat == null || b.lon == null) continue;
        if (pointInGeometry(b.lon, b.lat, f.geometry)) {
          const u = getUrgency(b);
          const rank = RANK.indexOf(u.level);
          if (rank > worst) { worst = rank; color = u.color; }
        }
      }
      f.properties = { ...f.properties, urgencyColor: color };
    }
    return fc;
  }, [bridges]);

  // init once — deferred so React StrictMode's double-mount in dev doesn't
  // create two WebGL contexts (the first cleanup cancels the timer).
  useEffect(() => {
    let ro: ResizeObserver | null = null;

    const timer = setTimeout(() => {
      const container = containerRef.current;
      if (mapRef.current || !container) return;

      try {
        const map = new maplibregl.Map({
          container,
          style: {
            version: 8,
            sources: {},
            layers: [{ id: 'bg', type: 'background', paint: { 'background-color': cssVar('--map-bg') } }],
          },
          bounds: FIT_BOUNDS,
          fitBoundsOptions: { padding: PADDING },
          maxBounds: MAX_BOUNDS,
          dragRotate: false,
          pitchWithRotate: false,
          attributionControl: false,
        });
        map.touchZoomRotate.disableRotation();
        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
        mapRef.current = map;
        map.on('error', (e: any) => setErr(e?.error?.message ?? String(e?.type ?? 'maplibre error')));

        map.on('load', () => {
          map.resize(); // container may not have had its size at creation
          map.addSource('states', { type: 'geojson', data: tintedGeo });
          map.addLayer({
            id: 'states-fill', type: 'fill', source: 'states',
            paint: { 'fill-color': fillExpr(cssVar('--map-region')), 'fill-opacity': 0.75 },
          });
          map.addLayer({
            id: 'states-line', type: 'line', source: 'states',
            paint: { 'line-color': cssVar('--map-stroke'), 'line-width': 1.8 },
          });
          map.fitBounds(FIT_BOUNDS, { padding: PADDING, duration: 0 });
          setLoaded(true);
        });

        ro = new ResizeObserver(() => map.resize());
        ro.observe(container);
      } catch (e: any) {
        setErr(`init: ${e?.message ?? e}`);
      }
    }, 80);

    return () => {
      clearTimeout(timer);
      ro?.disconnect();
      markersRef.current.forEach((m) => m.remove());
      contractorMarkerRef.current?.remove();
      contractorMarkerRef.current = null;
      mapRef.current?.remove();
      mapRef.current = null;
      setLoaded(false);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // refresh choropleth data
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    (map.getSource('states') as maplibregl.GeoJSONSource | undefined)?.setData(tintedGeo);
  }, [tintedGeo, loaded]);

  // theme reactivity
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    map.setPaintProperty('bg', 'background-color', cssVar('--map-bg'));
    map.setPaintProperty('states-fill', 'fill-color', fillExpr(cssVar('--map-region')));
    map.setPaintProperty('states-line', 'line-color', cssVar('--map-stroke'));
  }, [resolved, loaded]);

  // markers — outer element is MapLibre's (positioning); inner dot is ours (visuals)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    for (const b of bridges) {
      if (b.lat == null || b.lon == null) continue;
      const u = getUrgency(b);
      const selected = b.id === selectedId;
      const size = selected ? 22 : 15;

      const el = document.createElement('div');
      el.style.cssText = 'cursor:pointer;width:0;height:0;';

      const dot = document.createElement('div');
      dot.style.cssText = `
        position:absolute;left:${-size / 2}px;top:${-size / 2}px;
        width:${size}px;height:${size}px;border-radius:50%;background:${u.color};
        border:2.5px solid rgba(255,255,255,.92);
        box-shadow:0 2px 8px rgba(0,0,0,.35);transition:transform .15s ease;
        --pulse:${u.color}88;`;
      if (u.level === 'kritisch' || selected) dot.style.animation = 'pulse-ring 2s infinite';
      el.addEventListener('mouseenter', () => (dot.style.transform = 'scale(1.5)'));
      el.addEventListener('mouseleave', () => (dot.style.transform = 'scale(1)'));
      el.addEventListener('click', (e) => { e.stopPropagation(); onSelect(b); });
      el.appendChild(dot);

      markersRef.current.push(
        new maplibregl.Marker({ element: el }).setLngLat([b.lon, b.lat]).addTo(map),
      );
    }
  }, [bridges, selectedId, loaded, onSelect]);

  // contractor pin — a distinct blue marker with a name label, fit alongside the
  // selected bridge so the user sees the firm's position and distance at a glance.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;

    contractorMarkerRef.current?.remove();
    contractorMarkerRef.current = null;
    if (!contractor || contractor.lat == null || contractor.lon == null) return;

    const el = document.createElement('div');
    el.style.cssText = 'position:relative;display:grid;place-items:center;';
    const dot = document.createElement('div');
    dot.style.cssText =
      'width:26px;height:26px;border-radius:50%;background:#3b82f6;' +
      'border:3px solid #fff;box-shadow:0 3px 12px rgba(0,0,0,.45);' +
      'animation:pulse-ring 2s infinite;--pulse:#3b82f688;';
    const lbl = document.createElement('div');
    lbl.textContent = contractor.firmenname;
    lbl.style.cssText =
      'position:absolute;top:30px;left:50%;transform:translateX(-50%);' +
      'background:rgba(11,15,28,.92);color:#fff;border:1px solid #2c3a63;' +
      'padding:3px 9px;border-radius:8px;font:600 11px/1 Inter,sans-serif;' +
      'white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,.4);';
    el.append(dot, lbl);

    contractorMarkerRef.current = new maplibregl.Marker({ element: el, anchor: 'center' })
      .setLngLat([contractor.lon, contractor.lat])
      .addTo(map);

    const b = bridges.find((x) => x.id === selectedId);
    if (b && b.lat != null && b.lon != null) {
      const bounds = new maplibregl.LngLatBounds([b.lon, b.lat], [b.lon, b.lat]);
      bounds.extend([contractor.lon, contractor.lat]);
      map.fitBounds(bounds, {
        padding: { left: 600, top: 100, right: 90, bottom: 100 },
        maxZoom: 11,
        duration: 800,
      });
    }
  }, [contractor, loaded]); // eslint-disable-line react-hooks/exhaustive-deps

  // shift map viewport right when the panel is open so content isn't covered
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;

    if (selectedId) {
      const b = bridges.find((x) => x.id === selectedId);
      if (!b || b.lat == null) return;
      map.easeTo({
        center: [b.lon, b.lat],
        padding: { left: 560, top: 0, right: 0, bottom: 0 },
        zoom: Math.max(map.getZoom(), 6.2),
        duration: 800,
      });
    } else {
      map.easeTo({
        padding: { left: 0, top: 0, right: 0, bottom: 0 },
        duration: 600,
      });
    }
  }, [selectedId, loaded]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="h-full w-full" />

      {!loaded && !err && (
        <div className="absolute inset-0 z-10 grid place-items-center bg-background">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-primary" />
        </div>
      )}

      {err && (
        <div className="absolute left-1/2 top-1/2 z-30 w-[80%] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-xl border border-destructive/50 bg-destructive/10 p-4 text-center text-sm text-destructive">
          <p className="font-semibold">MapLibre-Fehler</p>
          <p className="mt-1 break-words font-mono text-xs">{err}</p>
        </div>
      )}

      {/* legend */}
      <div className="glass absolute bottom-5 right-5 z-10 rounded-2xl p-3.5 shadow-xl">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Dringlichkeit</p>
        <div className="space-y-1.5">
          {URGENCY_LEVELS.map((l) => {
            const { label, color } = urgencyMeta(l);
            return (
              <div key={l} className="flex items-center gap-2 text-xs">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
                <span className="text-muted-foreground">{label}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
