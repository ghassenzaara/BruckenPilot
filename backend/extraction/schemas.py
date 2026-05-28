"""Phase 4 — Pydantic v2 models: the LLM contract.

These are the shapes Gemini must return. Pydantic enforces them; the domain
gate in llm_extract.py enforces the semantic rules (grade ranges, index bounds).

German number formats are normalized by the LLM before returning:
  decimal comma  →  point      (2,2 → 2.2)
  thousands dot  →  stripped   (1.776,57 → 1776.57)
  DD.MM.YYYY     →  ISO date   (20.08.2025 → 2025-08-20)
"""
from pydantic import BaseModel, Field


class SourcePage(BaseModel):
    """One field → page-number reference (the audit trail). A list of these is
    used instead of a dict because the Gemini Developer API rejects the
    `additionalProperties` that a free-form dict[str,int] produces in the schema."""
    field: str            # e.g. "bauwerksnummer", "aktuelle_zustandsnote"
    page: int | None = None   # 1-based page; None when the model can't place it


class PruefungExtraction(BaseModel):
    art: str | None = None                  # Haupt / Einfache / Sonder
    datum: str | None = None               # ISO date string YYYY-MM-DD
    zustandsnote: float | None = None      # 1.0–4.0
    zyklus_monate: int | None = None


class SchadenExtraction(BaseModel):
    schaden_nr: int | None = None          # [N] in the document
    bsp_id: str | None = None             # e.g. "014-23"
    bauteil: str | None = None
    beschreibung: str | None = None
    ort: str | None = None
    s: int | None = Field(None, ge=0, le=4)
    v: int | None = Field(None, ge=0, le=4)
    d: int | None = Field(None, ge=0, le=4)

    # The damage's "Bild:" reference, copied VERBATIM by the LLM (a text copy
    # task, not visual matching). Its leading words equal the on-page photo
    # caption — the key photo_match.assign() uses to resolve the photo link.
    bild_ref: str | None = None

    # Photo link — set DETERMINISTICALLY by photo_match.assign() (not the LLM):
    foto_key: str | None = None        # Storage filename stem, derived from bild_ref
    foto_index: int | None = None      # 0-based index into the ExtractedImage list


class EmpfehlungExtraction(BaseModel):
    """Section 7.6 Empfehlungen — one 'Maßnahmenempfehlung {n}'. The inspector's
    recommended measure, tied to the damages it addresses. (This replaces the old
    8.3 Maßnahmen extraction: 7.6 is recommendations + damage links; 8.3 was
    executed works without a damage link.)"""
    nr: int | None = None                  # the {n} recommendation id
    art_der_leistung: str | None = None    # "Art der Leistung" line
    dringlichkeit: str | None = None
    geschaetzte_kosten_eur: float | None = None
    ausfuehrungsjahr: int | None = None
    bemerkung: str | None = None
    # Damage numbers ([n]) under this recommendation's "Zugeordnete Schäden:" list.
    # The authoritative link is re-derived deterministically from the text in the
    # pipeline (pdf_text.empfehlung_links); the LLM's value here is a fallback.
    zugeordnete_schaeden: list[int] = []


class BridgeExtraction(BaseModel):
    # ── identity ─────────────────────────────────────────────────────────────
    bauwerksnummer: str                    # required — natural upsert key
    interne_bwnr: str | None = None
    name: str | None = None
    ort: str | None = None
    strasse: str | None = None
    strassenklasse: str | None = None      # A / B / St / L / K / sonstige
    bundesland: str | None = None

    # ── location (raw UTM from the document — converted to WGS84 in Phase 5) ─
    utm_rechtswert: float | None = None
    utm_hochwert: float | None = None
    utm_bezugssystem: str | None = None    # e.g. "ETRS89 / UTM Zone 32N"

    # ── ownership ────────────────────────────────────────────────────────────
    amt: str | None = None
    meisterei: str | None = None
    baulast: str | None = None

    # ── structure ────────────────────────────────────────────────────────────
    baujahr_ueberbau: int | None = None
    baujahr_unterbau: int | None = None
    bauwerksart: str | None = None
    konstruktion: str | None = None
    hauptbaustoff: str | None = None
    laenge_m: float | None = None
    breite_m: float | None = None
    brueckenflaeche_m2: float | None = None
    anzahl_felder: int | None = None
    stuetzweite_max_m: float | None = None

    # ── load capacity ────────────────────────────────────────────────────────
    tragfaehigkeit_din: str | None = None
    mlc_einbahn: str | None = None
    mlc_zweibahn: str | None = None
    nachrechnung_vorhanden: bool | None = None

    # ── traffic ──────────────────────────────────────────────────────────────
    dtv_gesamt: int | None = None
    dtv_jahr: int | None = None
    lkw_anteil_pct: float | None = None
    umfahrt_pkw: str | None = None         # leicht/mittel/schwer/nicht_moeglich
    umfahrt_schwer: str | None = None
    umfahrt_oepnv: str | None = None

    # ── Bewertung (Abschnitt 7.5) — verbatim explanation under each max S/V/D ─
    # The document's own reasoning for the worst rating in each safety dimension
    # (which damages drive it). One paragraph per dimension; null when the doc
    # doesn't state one (older templates, scans where 7.5 didn't OCR cleanly).
    max_s_begruendung: str | None = None
    max_v_begruendung: str | None = None
    max_d_begruendung: str | None = None

    # ── children ─────────────────────────────────────────────────────────────
    pruefungen: list[PruefungExtraction] = []
    schaeden: list[SchadenExtraction] = []
    empfehlungen: list[EmpfehlungExtraction] = []

    # ── source linking ───────────────────────────────────────────────────────
    # Page references for headline values (audit-trail differentiator). Populate
    # for key fields only: bauwerksnummer, aktuelle Zustandsnote,
    # baujahr_ueberbau, dtv_gesamt. Stored as a {field: page} dict in the DB.
    source_pages: list[SourcePage] = []
