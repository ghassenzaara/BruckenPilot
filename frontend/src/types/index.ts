export interface PriorityBreakdown {
  priority_score: number;
  condition?: { value: number; zustandsnote?: number; max_s?: number; max_v?: number };
  criticality?: { value: number; roadclass?: string; dtv?: number; umfahrt_schwer?: string };
  cost_estimate?: { est_cost_eur?: number; brueckenflaeche_m2?: number };
  multipliers?: { importance: number };
  formula?: string;
}

export interface Bridge {
  id: string;
  bauwerksnummer: string;
  name: string;
  ort: string;
  strasse?: string;
  strassenklasse?: string;
  bundesland?: string;
  lat: number;
  lon: number;

  aktuelle_zustandsnote?: number;
  aktuelle_pruefung_datum?: string;
  aktuelle_pruefung_art?: string;
  max_s?: number;
  max_v?: number;
  max_d?: number;
  max_s_begruendung?: string;
  max_v_begruendung?: string;
  max_d_begruendung?: string;

  baujahr_ueberbau?: number;
  baujahr_unterbau?: number;
  bauwerksart?: string;
  konstruktion?: string;
  hauptbaustoff?: string;
  laenge_m?: number;
  breite_m?: number;
  brueckenflaeche_m2?: number;
  anzahl_felder?: number;

  dtv_gesamt?: number;
  lkw_anteil_pct?: number;
  umfahrt_schwer?: string;
  baulast?: string;
  amt?: string;
  meisterei?: string;

  priority_score?: number;
  priority_breakdown?: PriorityBreakdown;
  geschaetzte_kosten_eur?: number;

  intelligent_summary?: {
    situation: string;
    risiken: string;
    empfehlung: string;
  };
  benoetigte_leistungsbereiche?: string[];
  source_pages?: Record<string, number>;

  source_pdf_storage_path?: string;
  source_pdf_filename?: string;
}

export interface Contractor {
  id: string;
  pq_nummer?: string;
  firmenname: string;
  ort: string;
  plz?: string;
  strasse?: string;
  telefon?: string;
  email?: string;
  lat: number;
  lon: number;
  leistungsbereiche: string[];
  spezialisierungen?: string;
}

export interface Schaden {
  id: string;
  schaden_nr: number;
  bauteil: string;
  beschreibung: string;
  ort: string;
  bsp_id: string;
  s: number;
  v: number;
  d: number;
  foto_id?: string;
  foto_storage_path?: string;
}

export interface Pruefung {
  id: string;
  datum: string;
  art: string;
  zustandsnote: number;
}

/** Section 7.6 Maßnahmenempfehlung — a recommended measure linked to damages. */
export interface Empfehlung {
  id: string;
  nr?: number;
  art_der_leistung?: string;
  dringlichkeit?: string;
  geschaetzte_kosten_eur?: number;
  ausfuehrungsjahr?: number;
  bemerkung?: string;
  zugeordnete_schaeden?: number[];
}
