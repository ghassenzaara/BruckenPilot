import type { Bridge } from '@/types';

export type UrgencyLevel = 'kritisch' | 'hoch' | 'mittel' | 'niedrig' | 'unbekannt';

export interface Urgency {
  level: UrgencyLevel;
  label: string;
  color: string;   // hex for map markers / charts
  score: number;   // priority_score (0–1) or derived
}

const META: Record<UrgencyLevel, { label: string; color: string }> = {
  kritisch:   { label: 'Kritisch',  color: '#ef4444' },
  hoch:       { label: 'Hoch',      color: '#f97316' },
  mittel:     { label: 'Mittel',    color: '#eab308' },
  niedrig:    { label: 'Niedrig',   color: '#22c55e' },
  unbekannt:  { label: 'Unbekannt', color: '#94a3b8' },
};

/**
 * Urgency is driven by priority_score (the backend's urgency engine). Falls back
 * to Zustandsnote when no score exists. Thresholds chosen so the sample bridges
 * spread across all four bands.
 */
export function getUrgency(bridge: Bridge): Urgency {
  const score = bridge.priority_score;
  let level: UrgencyLevel;

  if (score != null) {
    level = score >= 0.4 ? 'kritisch'
          : score >= 0.3 ? 'hoch'
          : score >= 0.2 ? 'mittel'
          : 'niedrig';
  } else if (bridge.aktuelle_zustandsnote != null) {
    const z = bridge.aktuelle_zustandsnote;
    level = z >= 3.5 ? 'kritisch' : z >= 3.0 ? 'hoch' : z >= 2.0 ? 'mittel' : 'niedrig';
  } else {
    level = 'unbekannt';
  }

  return { level, ...META[level], score: score ?? 0 };
}

export const URGENCY_LEVELS: UrgencyLevel[] = ['kritisch', 'hoch', 'mittel', 'niedrig'];
export const urgencyMeta = (l: UrgencyLevel) => META[l];
