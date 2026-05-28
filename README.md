# 🌉 BrückenPilot

**Turning German bridge-inspection PDFs into a live, map-based infrastructure monitoring platform — fully automated.**

Every German bridge is inspected under **DIN 1076**, producing a *Bauwerksbuch* — a 20–90 page PDF with the bridge's attributes, full inspection history, every individual damage with photos, and recommended measures. BrückenPilot reads those PDFs end-to-end and turns them into structured, searchable, prioritized intelligence on an interactive map.

See [`ARCHITECTURE_FINAL.md`](./ARCHITECTURE_FINAL.md) for the full system diagram.

---

## How it works (the pipeline)

Each PDF runs through a deterministic, auditable batch pipeline (`backend/pipeline.py`). Every step is isolated — one bad PDF never breaks the batch — and a SHA-256 hash makes re-runs idempotent.

| # | Step | What happens |
|---|------|--------------|
| 1 | **Text & OCR** | Read the text layer with page markers. If a page averages < 50 chars it's an image-only **scan** → re-read with **Tesseract OCR (German)**. |
| 2 | **Photo extraction** | Locate section 7.4 (Schäden) and pull its photos. Digital → embedded image objects. Scan → embedded images above a pixel threshold (filtering text strips) with **stacked tiles stitched**; a flat page falls back to **DocLayout-YOLO** cropping figure regions. |
| 3 | **Structured LLM extraction** | One call returns the full record (identity, coordinates, inspection history, every damage with S/V/D ratings, section 7.6 recommendations), validated against a strict **Pydantic** schema with domain sanity gates. |
| 3b | **Deterministic linking** *(no LLM)* | Photos bound to damages by caption; recommendations linked to the damages they address — both from the document's own markers (see below). |
| 4 | **Coordinates** | Convert the document's **UTM (ETRS89) → WGS84** with the correct zone; ignore Gauß-Krüger. No coordinates → **geocode the address** as an approximate pin, flagged `geocoded` vs `utm`. |
| 5 | **Priority scoring** | A transparent score from **`condition × (0.5 + 0.5·criticality)`** (grade & severity, road class, traffic, detour difficulty). Every factor is stored — no black-box metric. |
| 6 | **Contractor matching** | The construction type determines the required PQ service categories; the frontend filters qualified firms by capability and distance. |
| 7 | **Intelligent summary** | A second LLM call writes a short three-part read — *Situation · Risiken · Empfehlung*. The only generated prose. |
| 8 | **Persist** | PDF, matched photos and all records upserted to Supabase — idempotent, no duplicates. |

### Key innovations

- **The `[ ]` damage-count trick.** On long documents the LLM quietly drops damages (e.g. 61 of 65). In section 7.4 every damage begins with a bracketed marker like `[19] S=…`; we count those markers with a regex (`pdf_text.schaeden_marker_numbers`) — the **exact, deterministic count N**. Description brackets like `[Längsriss]` never match.
- **Self-correcting LLM retry.** We diff the returned damages against the marker numbers, compute **exactly which `[n]` are missing**, and re-ask — naming those numbers and nudging the temperature up. We keep whichever pass is closest to N, so a retry can only help (`pipeline._llm_extract`).
- **Deterministic photo ↔ damage matching.** Each damage carries a verbatim `Bild:` reference equal to its on-page caption. Digital → prefix-match from the text layer; scan → OCR the caption and match on its discriminating ID token. No confident match → no photo (honest over guessing).
- **7.6 Empfehlungen + linking.** Section 7.6 tags each measure `Maßnahmenempfehlung {n}` and lists its `Zugeordnete Schäden: [a],[b]`. We parse the `{n}` and bracket IDs deterministically (filtered to the real damage set), so every recommendation links to its exact damages (`pdf_text.empfehlung_links`).
- **Scan handling.** A document with effectively no text layer is auto-detected and OCR'd; the rest of the pipeline is identical downstream.

### LLM backends

Two interchangeable providers behind one shared prompt & schema:

- **Llama 4 Maverick** via DigitalOcean Gradient — **primary**, not quota-capped. Active whenever `DO_MODEL_ACCESS_KEY` is set.
- **Gemini** — fallback / alternative (free tier is rate-limited). Used when the DO key is absent, or as a failure fallback when `LLM_GEMINI_FALLBACK=1`.

---

## Frontend

A real-time React dashboard that reads **directly from Supabase** (no backend server). Deployed on Vercel.

- **Map view** — choropleth of Germany, every bridge a marker coloured by urgency; states tinted by their worst bridge.
- **List view** ("Alle Brücken") — bridge cards ranked by condition & priority.
- **Search** — live dropdown finds any bridge by name / Bauwerksnummer / Ort and jumps straight to it.
- **Urgency filter** — toggle Kritisch / Hoch / Mittel / Niedrig with live counts.
- **Detail panel** (3 tabs):
  - **Allgemein** — Zustandsnote, worst **S/V/D** ratings (click each for the document's verbatim 7.5 *Begründung* in a popover), priority score, estimated cost, traffic (DTV), road class, full inspection-history chart, Stammdaten, and the AI *KI-Einschätzung*.
  - **Schäden** — damage cards with matched photos (full-screen lightbox), and a **🔧 Maßnahmenempfehlung** link that opens the connected 7.6 recommendation in a floating window.
  - **Firmen** — PQ-qualified contractors matched by capability and a live **distance slider**; each firm has a **Google Maps** deep-link and an **"Auf Karte zeigen"** button that drops a labelled pin on the map and fits the view to bridge + firm.
- **Source PDF** — one click opens the original Bauwerksbuch in an inline viewer (the audit trail).
- **Adaptive theme** — full light & dark.

---

## Tech stack

| Layer | Tools |
|-------|-------|
| **Pipeline** | Python · pdfplumber · PyMuPDF · Tesseract OCR · DocLayout-YOLO · pyproj · Pydantic v2 · Llama 4 Maverick / Gemini |
| **Frontend** | React 19 · TypeScript · Vite · Tailwind CSS · MapLibre GL · Recharts · Framer Motion · TanStack Query |
| **Infrastructure** | Supabase (Postgres + Storage + RLS) · Nominatim geocoding · PQ-Verein registry · Vercel (frontend) |

---

## Repository layout

```
backend/
  pipeline.py            # phases 3→8 wired into one run(pdf)
  run_overnight.py       # batch runner over a folder of PDFs
  config.py              # env-driven settings (LLM keys, OCR, buckets…)
  ingestion/             # pdf_text (text/OCR/markers), pdf_photos, photo_crop, photo_match, ocr
  extraction/            # schemas (Pydantic), llm_extract (Gemini), do_extract (Llama)
  enrichment/            # scoring, coords, geocode, matching, summary/do_summary
  persistence/           # upsert (idempotent), storage
  domain/                # mappings (scoring tables, road-class & cost rates)
  db/schema.sql          # single source of truth for the database
  contractors/seed.py    # one-time contractor seeding
frontend/                # React + Vite app (deployed to Vercel)
presentation/            # project showcase (index.html + screenshots)
ARCHITECTURE_FINAL.md    # system diagram
```

---

## Running it

### Database
Apply `backend/db/schema.sql` in the Supabase SQL editor (it's the single source of truth — keeps the live DB and code in sync).

### Backend pipeline
```bash
pip install -r requirements.txt
# configure .env (see below), then run the batch over your PDF folder:
python -m backend.run_overnight
```
Switch LLM backend by setting (or clearing) `DO_MODEL_ACCESS_KEY` in `.env` — set = Llama, unset = Gemini.

### Frontend (dev)
```bash
cd frontend
npm install
npm run dev
```

---

## Deployment (Vercel)

The frontend lives in the `frontend/` subdirectory of the repo.

| Setting | Value |
|---|---|
| **Root Directory** | `frontend` |
| **Framework Preset** | Vite |
| **Install Command** | `npm install` |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |

Add the two frontend env vars in Vercel (Production + Preview): `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.

---

## Environment variables

**Backend (`.env` at repo root):**
```
SUPABASE_URL=…
SUPABASE_SERVICE_KEY=…          # service-role — backend only, never in the frontend
DO_MODEL_ACCESS_KEY=…           # set → use Llama (DigitalOcean); unset → use Gemini
LLM_MODEL=llama-4-maverick
GEMINI_API_KEY=…                # used as fallback / when DO key is absent
GEMINI_MODEL=gemini-2.5-flash
LLM_GEMINI_FALLBACK=0           # 1 = fall back to Gemini if a DO call fails
TESSERACT_CMD=…                 # path to tesseract.exe on Windows (OCR for scans)
```

**Frontend (`frontend/.env`):**
```
VITE_SUPABASE_URL=…
VITE_SUPABASE_ANON_KEY=…        # public by design; protected by Row-Level Security
```

> The anon key is safe to expose. The service-role key and LLM keys must **never** ship in the frontend.

---

## Design principles

Deterministic over guessing · Source-linked & auditable · Idempotent re-runs · Honest gaps (no fabricated photos/links) · Batch isolation (one PDF failure ≠ batch failure).
