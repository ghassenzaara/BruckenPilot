-- ============================================================================
-- BrückenPilot — database schema (single source of truth)
-- Apply in the Supabase SQL editor (or via psql).
-- ============================================================================

create extension if not exists pgcrypto;  -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- DESTRUCTIVE RESET — uncomment to wipe and rebuild during development.
-- ---------------------------------------------------------------------------
-- drop table if exists extraction_jobs cascade;
-- drop table if exists massnahmen     cascade;
-- drop table if exists schaeden       cascade;
-- drop table if exists pruefungen     cascade;
-- drop table if exists contractors    cascade;
-- drop table if exists bridges        cascade;

-- ============================================================
-- bridges — central entity, one row per Bauwerk
-- ============================================================
create table bridges (
  id                          uuid primary key default gen_random_uuid(),

  -- identity
  bauwerksnummer              text unique not null,   -- NATURAL KEY for upsert
  interne_bwnr                text,
  name                        text,
  ort                         text,
  strasse                     text,
  strassenklasse              text check (strassenklasse in
                                ('A','B','St','L','K','sonstige')),
  bundesland                  text,

  -- location
  lat                         double precision,       -- WGS84, from pyproj
  lon                         double precision,
  utm_rechtswert              double precision,
  utm_hochwert                double precision,
  utm_bezugssystem            text,                    -- drives UTM zone (32N/33N)

  -- ownership
  amt                         text,
  meisterei                   text,
  baulast                     text,

  -- structure
  baujahr_ueberbau            int,
  baujahr_unterbau            int,
  bauwerksart                 text,
  konstruktion                text,
  hauptbaustoff               text,
  laenge_m                    numeric,
  breite_m                    numeric,
  brueckenflaeche_m2          numeric,
  anzahl_felder               int,
  stuetzweite_max_m           numeric,

  -- load capacity
  tragfaehigkeit_din          text,
  mlc_einbahn                 text,
  mlc_zweibahn                text,
  nachrechnung_vorhanden      boolean,

  -- traffic
  dtv_gesamt                  int,
  dtv_jahr                    int,
  lkw_anteil_pct              numeric,
  umfahrt_pkw                 text check (umfahrt_pkw in
                                ('leicht','mittel','schwer','nicht_moeglich')),
  umfahrt_schwer              text check (umfahrt_schwer in
                                ('leicht','mittel','schwer','nicht_moeglich')),
  umfahrt_oepnv               text,

  -- denormalized current state (latest pruefung / worst schaden)
  aktuelle_zustandsnote       numeric(3,1),
  aktuelle_substanznote       numeric(3,1),
  aktuelle_pruefung_datum     date,
  aktuelle_pruefung_art       text,
  naechste_hauptpruefung_faellig int,
  max_s                       smallint check (max_s between 0 and 4),
  max_v                       smallint check (max_v between 0 and 4),
  max_d                       smallint check (max_d between 0 and 4),

  -- scoring (Phase 5)
  priority_score              numeric,                 -- 0–1
  priority_breakdown          jsonb,                   -- the 4 factors, explainable
  empfohlene_massnahme        text,
  geschaetzte_kosten_eur      numeric,

  -- LLM summary (Phase 5): {situation, risiken, empfehlung}
  intelligent_summary         jsonb,

  -- capability set computed in batch; frontend filters by distance in-browser.
  -- stored verbatim in the PQ underscore format, e.g. ["311_01","613_01"]
  benoetigte_leistungsbereiche jsonb,

  -- source linking — {field_name: page_number}, powers the audit trail
  source_pages                jsonb,

  -- provenance
  source_pdf_storage_path     text,
  source_pdf_filename         text,
  source_job_id               uuid,

  extracted_at                timestamptz,
  created_at                  timestamptz default now(),
  updated_at                  timestamptz default now()
);

-- ============================================================
-- pruefungen — inspection history (1 bridge : many)
-- ============================================================
create table pruefungen (
  id            uuid primary key default gen_random_uuid(),
  bridge_id     uuid not null references bridges(id) on delete cascade,
  art           text,                                   -- Haupt/Einfache/Sonder
  datum         date,
  zustandsnote  numeric(3,1),
  substanznote  numeric(3,1),
  zyklus_monate int
);
create index on pruefungen (bridge_id);

-- ============================================================
-- schaeden — individual damages (1 bridge : many)
-- ============================================================
create table schaeden (
  id                uuid primary key default gen_random_uuid(),
  bridge_id         uuid not null references bridges(id) on delete cascade,
  schaden_nr        int,                                -- [N] bridge-wide id
  bsp_id            text,                               -- e.g. "252-08"
  bauteil           text,
  beschreibung      text,
  ort               text,
  s                 smallint check (s between 0 and 4),
  v                 smallint check (v between 0 and 4),
  d                 smallint check (d between 0 and 4),
  foto_id           text,                               -- "Bild:" reference
  foto_storage_path text
);
create index on schaeden (bridge_id);
-- query-time sort: order by s desc, v desc, d desc

-- ============================================================
-- massnahmen — past maintenance (1 bridge : many)
-- ============================================================
create table massnahmen (
  id            uuid primary key default gen_random_uuid(),
  bridge_id     uuid not null references bridges(id) on delete cascade,
  massnahme_nr  text,                                   -- {N} internal ref
  jahr          int,
  art           text,
  beschreibung  text,
  auftragnehmer text,                                   -- historical contractor
  auftragssumme numeric,
  waehrung      text check (waehrung in ('DM','EUR')),
  flaeche_m2    numeric,
  bemerkung     text
);
create index on massnahmen (bridge_id);

-- ============================================================
-- extraction_jobs — one row per processed PDF (audit + resumability)
-- ============================================================
create table extraction_jobs (
  id                     uuid primary key default gen_random_uuid(),
  pdf_filename           text,
  pdf_storage_path       text,
  pdf_size_bytes         bigint,
  pdf_sha256             text,                          -- dedup / skip key
  status                 text not null default 'pending'
                           check (status in
                             ('pending','processing','completed','failed')),
  status_message         text,
  bridge_id              uuid references bridges(id),
  error_message          text,
  started_at             timestamptz,
  completed_at           timestamptz,
  extraction_duration_ms int,
  llm_model              text,
  llm_input_tokens       int,
  llm_output_tokens      int,
  created_at             timestamptz default now()
);
create index on extraction_jobs (pdf_sha256);
create index on extraction_jobs (status);

-- ============================================================
-- contractors — seeded separately (Phase 2), standalone
-- ============================================================
create table contractors (
  id                uuid primary key default gen_random_uuid(),
  pq_nummer         text unique,                        -- "PPP.NNNNNN"
  firmenname        text,
  strasse           text,
  plz               text,
  ort               text,
  land              text,
  telefon           text,                               -- present in source data
  email             text,                               -- present in source data
  lat               double precision,                  -- geocoded
  lon               double precision,
  leistungsbereiche text[],                             -- ["311_01","613_01"]
  spezialisierungen text                                -- comma-separated raw text
);
-- GIN index enables fast overlap (&&) queries for capability matching
create index on contractors using gin (leistungsbereiche);
