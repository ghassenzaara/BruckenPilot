import { useState } from 'react';
import { motion } from 'framer-motion';
import { X, FileText } from 'lucide-react';
import type { Bridge, Contractor } from '@/types';
import { useBridgeDetails, useContractors } from '@/hooks/useSupabase';
import { getUrgency } from '@/lib/urgency';
import { cn } from '@/lib/utils';
import { GeneralTab } from './GeneralTab';
import { DamagesTab } from './DamagesTab';
import { ContractorsTab } from './ContractorsTab';
import { PdfViewer } from './PdfViewer';

type Tab = 'allgemein' | 'schaeden' | 'kontraktoren';

export function BridgePanel({
  bridge, onClose, pinnedContractorId, onPinContractor,
}: {
  bridge: Bridge;
  onClose: () => void;
  pinnedContractorId?: string;
  onPinContractor?: (c: Contractor) => void;
}) {
  const [tab, setTab] = useState<Tab>('allgemein');
  const [pdfOpen, setPdfOpen] = useState(false);
  const { data: details } = useBridgeDetails(bridge.id);
  const { data: contractors } = useContractors();
  const urgency = getUrgency(bridge);

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: 'allgemein', label: 'Allgemein' },
    { id: 'schaeden', label: 'Schäden', count: details?.schaeden?.length },
    { id: 'kontraktoren', label: 'Firmen' },
  ];

  return (
    <motion.div
      initial={{ x: -40, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: -40, opacity: 0 }}
      transition={{ type: 'spring', damping: 26, stiffness: 260 }}
      className="glass absolute left-4 top-4 bottom-4 z-20 flex w-[540px] max-w-[calc(100%-2rem)] flex-col overflow-hidden rounded-3xl shadow-2xl"
    >
      {/* header */}
      <div className="relative shrink-0 border-b p-5">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 grid h-8 w-8 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
        <div className="mb-2 flex items-center gap-2">
          <span
            className="rounded-full px-2.5 py-0.5 text-xs font-bold text-white"
            style={{ background: urgency.color }}
          >
            {urgency.label}
          </span>
          <span className="text-xs text-muted-foreground tabular-nums">Nr. {bridge.bauwerksnummer}</span>
        </div>
        <h2 className="pr-8 text-lg font-bold leading-tight tracking-tight">{bridge.name || 'Unbenanntes Bauwerk'}</h2>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {[bridge.ort, bridge.strasse].filter(Boolean).join(' · ')}
        </p>

        {/* PDF button */}
        {bridge.source_pdf_storage_path && (
          <button
            onClick={() => setPdfOpen(true)}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border bg-background/60 px-4 py-2.5 text-sm font-semibold transition-colors hover:bg-accent hover:text-foreground"
          >
            <FileText className="h-4 w-4 text-primary" />
            Bauwerksbuch PDF öffnen
          </button>
        )}
      </div>

      {/* tabs */}
      <div className="flex shrink-0 gap-1 px-4 pt-3">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              'flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-sm font-medium transition-colors',
              tab === t.id ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent',
            )}
          >
            {t.label}
            {t.count != null && (
              <span className={cn('rounded px-1 text-[10px] tabular-nums', tab === t.id ? 'bg-white/25' : 'bg-muted')}>
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* body */}
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {tab === 'allgemein' && <GeneralTab bridge={bridge} pruefungen={details?.pruefungen ?? []} />}
        {tab === 'schaeden' && (
          <DamagesTab schaeden={details?.schaeden ?? []} empfehlungen={details?.empfehlungen ?? []} />
        )}
        {tab === 'kontraktoren' && (
          <ContractorsTab
            bridge={bridge}
            contractors={contractors ?? []}
            pinnedId={pinnedContractorId}
            onPin={onPinContractor}
          />
        )}
      </div>

      {pdfOpen && bridge.source_pdf_storage_path && (
        <PdfViewer
          path={bridge.source_pdf_storage_path}
          filename={bridge.source_pdf_filename}
          onClose={() => setPdfOpen(false)}
        />
      )}
    </motion.div>
  );
}
