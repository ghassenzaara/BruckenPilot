import { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X, ZoomIn, Wrench } from 'lucide-react';
import type { Schaden, Empfehlung } from '@/types';
import { getSignedPhotoUrl } from '@/lib/storage';

function svdColor(v: number) {
  return v >= 3 ? '#ef4444' : v >= 2 ? '#f97316' : v >= 1 ? '#eab308' : '#22c55e';
}

const eur = (n?: number) =>
  n == null ? null : new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(n);

/* ─── Recommendation popover (section 7.6) ──────────────────────────────────
   A floating "window" anchored to the right of the clicked damage card. Rendered
   in a portal with fixed positioning so the drawer's overflow can't clip it; flips
   to the left edge when there isn't room on the right. */
function EmpfehlungPopover({
  items, anchor, onClose,
}: { items: Empfehlung[]; anchor: DOMRect; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const W = 360;
  let left = anchor.right + 12;
  if (left + W > window.innerWidth - 8) left = Math.max(8, anchor.left - W - 12);
  const top = Math.min(Math.max(8, anchor.top), Math.max(8, window.innerHeight - 320));

  return createPortal(
    <>
      <div className="fixed inset-0 z-[9998]" onClick={onClose} />
      <div
        role="dialog"
        className="fixed z-[9999] max-h-[72vh] w-[360px] overflow-y-auto rounded-2xl border-2 border-border bg-popover p-4 text-popover-foreground shadow-2xl ring-1 ring-black/10"
        style={{ left, top }}
      >
        <p className="mb-3 flex items-center gap-1.5 text-sm font-bold uppercase tracking-wide text-primary">
          <Wrench className="h-4 w-4" />
          {items.length > 1 ? `${items.length} Maßnahmenempfehlungen` : 'Maßnahmenempfehlung'}
        </p>
        <div className="space-y-3">
          {items.map((e) => (
            <div key={e.id} className="rounded-xl border border-border/60 bg-background/40 p-3">
              <div className="mb-1.5 flex items-center gap-2">
                <span className="rounded-md bg-muted px-2 py-0.5 text-sm font-semibold tabular-nums">
                  {`{${e.nr ?? '–'}}`}
                </span>
                {e.dringlichkeit && (
                  <span className="text-xs font-medium text-muted-foreground">{e.dringlichkeit}</span>
                )}
              </div>
              {e.art_der_leistung && (
                <p className="text-[15px] font-semibold leading-snug text-foreground">{e.art_der_leistung}</p>
              )}
              {e.bemerkung && (
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{e.bemerkung}</p>
              )}
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
                {eur(e.geschaetzte_kosten_eur) && (
                  <span className="font-semibold tabular-nums">{eur(e.geschaetzte_kosten_eur)}</span>
                )}
                {e.ausfuehrungsjahr != null && (
                  <span className="text-muted-foreground">Ausführung {e.ausfuehrungsjahr}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>,
    document.body,
  );
}

/* ─── Lightbox ─────────────────────────────────────────────────────────── */
function Lightbox({ url, alt, onClose }: { url: string; alt: string; onClose: () => void }) {
  // Close on Escape key
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={onClose}
    >
      {/* Close button */}
      <button
        onClick={onClose}
        className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white transition hover:bg-white/20"
      >
        <X className="h-5 w-5" />
      </button>

      {/* Image — stop click from bubbling to backdrop */}
      <div
        className="relative max-h-[90vh] max-w-[90vw] overflow-hidden rounded-2xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <img
          src={url}
          alt={alt}
          className="block max-h-[90vh] max-w-[90vw] object-contain"
          style={{ animation: 'lightbox-in 0.2s ease' }}
        />
        <p className="absolute bottom-0 left-0 right-0 bg-black/50 px-4 py-2 text-center text-xs text-white/80 backdrop-blur-sm">
          {alt} · ESC oder Klick zum Schließen
        </p>
      </div>

      <style>{`
        @keyframes lightbox-in {
          from { opacity: 0; transform: scale(0.92); }
          to   { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>,
    document.body,
  );
}

/* ─── Photo slot ────────────────────────────────────────────────────────── */
function PhotoSlot({ path, label }: { path: string; label: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [urlReady, setUrlReady] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getSignedPhotoUrl(path).then((signed) => {
      if (cancelled) return;
      if (!signed) setFailed(true);
      else { setUrl(signed); setUrlReady(true); }
    });
    return () => { cancelled = true; };
  }, [path]);

  const openLightbox = useCallback(() => {
    if (imgLoaded) setLightboxOpen(true);
  }, [imgLoaded]);

  if (failed) return null;

  return (
    <>
      <div
        className="group relative h-32 w-32 shrink-0 overflow-hidden rounded-xl border bg-muted"
        onClick={openLightbox}
        title="Klicken zum Vergrößern"
      >
        {/* Shimmer */}
        {(!urlReady || !imgLoaded) && (
          <div className="absolute inset-0 animate-pulse bg-muted" />
        )}

        {/* Image */}
        {urlReady && url && (
          <img
            src={url}
            alt={label}
            loading="lazy"
            onLoad={() => setImgLoaded(true)}
            onError={() => setFailed(true)}
            className={`h-full w-full object-cover transition-opacity duration-300 ${imgLoaded ? 'opacity-100' : 'opacity-0'}`}
          />
        )}

        {/* Zoom hint overlay on hover */}
        {imgLoaded && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-all duration-200 group-hover:bg-black/30 group-hover:opacity-100">
            <ZoomIn className="h-5 w-5 text-white drop-shadow" />
          </div>
        )}
      </div>

      {lightboxOpen && url && (
        <Lightbox url={url} alt={label} onClose={() => setLightboxOpen(false)} />
      )}
    </>
  );
}

/* ─── Damage card ───────────────────────────────────────────────────────── */
function DamageCard({ s, linked }: { s: Schaden; linked: Empfehlung[] }) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);

  const toggle = () => {
    if (anchor) { setAnchor(null); return; }
    if (cardRef.current) setAnchor(cardRef.current.getBoundingClientRect());
  };

  return (
    <div ref={cardRef} className="animate-in-up overflow-hidden rounded-2xl border bg-card/60">
      <div className="flex gap-4 p-5">
        <div className="min-w-0 flex-1">
          <div className="mb-2.5 flex items-center gap-2.5">
            <span className="rounded-md bg-muted px-2 py-0.5 text-sm font-semibold tabular-nums">
              #{s.schaden_nr}
            </span>
            <span className="truncate text-lg font-bold">{s.bauteil || 'Schaden'}</span>
          </div>
          <p className="text-[15px] leading-relaxed text-foreground/80">{s.beschreibung}</p>
          {s.ort && <p className="mt-2 text-sm text-muted-foreground">{s.ort}</p>}
          <div className="mt-3.5 flex items-center gap-2">
            {(['S', 'V', 'D'] as const).map((k) => {
              const v = s[k.toLowerCase() as 's' | 'v' | 'd'];
              return (
                <span
                  key={k}
                  className="rounded-md px-2.5 py-1 text-sm font-bold text-white"
                  style={{ background: svdColor(v) }}
                >
                  {k} {v}
                </span>
              );
            })}
            {s.bsp_id && <span className="ml-auto text-sm text-muted-foreground">BSP {s.bsp_id}</span>}
          </div>
        </div>

        {s.foto_storage_path && (
          <PhotoSlot path={s.foto_storage_path} label={s.bauteil || 'Schadensfoto'} />
        )}
      </div>

      {/* linked 7.6 recommendation(s) — opens a floating window to the right */}
      {linked.length > 0 && (
        <button
          onClick={toggle}
          aria-expanded={!!anchor}
          className="flex w-full items-center gap-2 border-t bg-background/40 px-5 py-2.5 text-sm font-semibold text-primary transition-colors hover:bg-accent"
        >
          <Wrench className="h-4 w-4" />
          {linked.length > 1
            ? `${linked.length} Maßnahmenempfehlungen`
            : `Maßnahmenempfehlung {${linked[0].nr}}`}
        </button>
      )}

      {anchor && (
        <EmpfehlungPopover items={linked} anchor={anchor} onClose={() => setAnchor(null)} />
      )}
    </div>
  );
}

/* ─── Tab ───────────────────────────────────────────────────────────────── */
export function DamagesTab({
  schaeden, empfehlungen,
}: { schaeden: Schaden[]; empfehlungen: Empfehlung[] }) {
  if (!schaeden.length) {
    return <p className="py-10 text-center text-sm text-muted-foreground">Keine Schäden erfasst.</p>;
  }
  // damage → its recommendations, by the deterministic 7.6 "Zugeordnete Schäden" link
  const linkedFor = (nr: number) =>
    empfehlungen.filter((e) => (e.zugeordnete_schaeden ?? []).includes(nr));

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{schaeden.length} Schäden · nach Schwere sortiert</p>
      {schaeden.map((s) => <DamageCard key={s.id} s={s} linked={linkedFor(s.schaden_nr)} />)}
    </div>
  );
}
