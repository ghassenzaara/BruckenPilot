import { useEffect, useState } from 'react';
import { X, Loader2, ExternalLink, AlertTriangle } from 'lucide-react';
import { getSignedPdfUrl } from '@/lib/storage';

/**
 * Full-screen inline PDF reader. Loads a signed URL for the object in the
 * `bauwerksbuecher` bucket and embeds it in an <iframe> (the browser's built-in
 * PDF viewer) — no popup, so it isn't blocked by popup blockers.
 */
export function PdfViewer({
  path,
  filename,
  onClose,
}: {
  path: string;
  filename?: string;
  onClose: () => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    setUrl(null);
    setError(false);
    getSignedPdfUrl(path).then((u) => {
      if (!active) return;
      if (u) setUrl(u);
      else setError(true);
    });
    return () => {
      active = false;
    };
  }, [path]);

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex items-center justify-between gap-2 p-3 text-white"
        onClick={(e) => e.stopPropagation()}
      >
        <span className="truncate text-sm font-semibold">{filename ?? 'Bauwerksbuch'}</span>
        <div className="flex items-center gap-2">
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 rounded-lg bg-white/10 px-3 py-1.5 text-xs font-medium hover:bg-white/20"
            >
              <ExternalLink className="h-3.5 w-3.5" /> Neuer Tab
            </a>
          )}
          <button
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-lg bg-white/10 hover:bg-white/20"
            aria-label="Schließen"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 p-3 pt-0" onClick={(e) => e.stopPropagation()}>
        {error ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 rounded-2xl bg-background p-6 text-center text-sm text-muted-foreground">
            <AlertTriangle className="h-7 w-7 text-amber-500" />
            <p className="font-medium text-foreground">PDF konnte nicht geladen werden.</p>
            <p className="max-w-sm text-xs">
              Der Bucket „bauwerksbuecher“ muss öffentlich sein oder eine Lese-Policy
              (SELECT) für die anon-Rolle besitzen.
            </p>
          </div>
        ) : url ? (
          <iframe
            src={url}
            title={filename ?? 'Bauwerksbuch PDF'}
            className="h-full w-full rounded-2xl border-0 bg-white"
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-7 w-7 animate-spin text-white" />
          </div>
        )}
      </div>
    </div>
  );
}
