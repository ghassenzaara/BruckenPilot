"""Phase 6 — idempotent persistence of one processed bridge.

`persist(...)` writes everything for a single PDF and is safe to re-run:
  - upload PDF + photos to Storage (deterministic paths → overwrite)
  - UPSERT the bridge on the natural key `bauwerksnummer`
  - REPLACE child rows (delete by bridge_id, then insert) — children have no
    stable cross-run key, so replace is the clean idempotent choice
  - denormalize current-state fields (latest pruefung, worst damage) onto bridge

Re-running with the same PDF yields identical row counts and content.
"""
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from backend.db.client import get_client
from backend.domain import mappings as M
from backend.extraction.schemas import BridgeExtraction
from backend.ingestion.pdf_photos import ExtractedImage
from backend.persistence import storage

log = logging.getLogger(__name__)

# Bridge columns that map 1:1 from BridgeExtraction fields.
_DIRECT_FIELDS = {
    "bauwerksnummer", "interne_bwnr", "name", "ort", "strasse", "strassenklasse",
    "bundesland", "utm_rechtswert", "utm_hochwert", "utm_bezugssystem",
    "amt", "meisterei", "baulast",
    "baujahr_ueberbau", "baujahr_unterbau", "bauwerksart", "konstruktion",
    "hauptbaustoff", "laenge_m", "breite_m", "brueckenflaeche_m2", "anzahl_felder",
    "stuetzweite_max_m", "tragfaehigkeit_din", "mlc_einbahn", "mlc_zweibahn",
    "nachrechnung_vorhanden", "dtv_gesamt", "dtv_jahr", "lkw_anteil_pct",
    "umfahrt_pkw", "umfahrt_schwer", "source_pages",
    "max_s_begruendung", "max_v_begruendung", "max_d_begruendung",
}

# ── small coercion helpers ──────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_iso(value) -> str | None:
    """Coerce a date-ish value to 'YYYY-MM-DD', or None if unparseable."""
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _normalize_bwnr(value: str) -> str:
    """Canonicalize the natural key. The LLM spaces the Teilbauwerk digit
    inconsistently ('5010710 2' vs '50107102'), so collapsing all whitespace
    keeps the upsert key stable across runs and prevents duplicate bridges."""
    return "".join(str(value).split())


def _summary_dict(summary):
    if summary is None:
        return None
    return summary.model_dump() if hasattr(summary, "model_dump") else summary


def _latest_pruefung(bridge: BridgeExtraction):
    dated = [p for p in bridge.pruefungen if p.datum]
    if dated:
        return max(dated, key=lambda p: str(p.datum))
    return bridge.pruefungen[-1] if bridge.pruefungen else None


# ── row builders (pure) ─────────────────────────────────────────────────────
def build_bridge_row(
    bridge: BridgeExtraction,
    *,
    coords: tuple[float, float] | None,
    coord_source: str | None,
    priority_score: float,
    priority_breakdown: dict,
    benoetigte_leistungsbereiche: list[str],
    intelligent_summary,
    pdf_storage_path: str,
    pdf_filename: str,
    job_id: str | None,
) -> dict:
    row = bridge.model_dump(include=_DIRECT_FIELDS)
    row["bauwerksnummer"] = _normalize_bwnr(bridge.bauwerksnummer)

    # normalize the LLM's free-text enums to the canonical codes the CHECK
    # constraints require ('Bundesautobahn' → 'A', 'Leicht möglich…' → 'leicht')
    # Road class is derived deterministically from the Strasse prefix ('L 2086'
    # → 'L'); fall back to the LLM's strassenklasse only if that can't be parsed.
    row["strassenklasse"] = (
        M.strassenklasse_from_strasse(row.get("strasse"))
        or M.normalize_strassenklasse(row.get("strassenklasse"))
    )
    row["umfahrt_pkw"] = M.normalize_umfahrt(row.get("umfahrt_pkw"))
    row["umfahrt_schwer"] = M.normalize_umfahrt(row.get("umfahrt_schwer"))

    # source_pages: list[{field, page}] (LLM shape) → {field: page} dict for the DB
    # (drop entries the model left without a page number)
    row["source_pages"] = {
        sp["field"]: sp["page"]
        for sp in (row.get("source_pages") or [])
        if sp.get("page") is not None
    }

    if coords:
        row["lat"], row["lon"] = coords
    row["coord_source"] = coord_source   # 'utm' | 'geocoded' (approximate) | None

    # denormalize: latest inspection
    latest = _latest_pruefung(bridge)
    if latest:
        row["aktuelle_zustandsnote"] = latest.zustandsnote
        row["aktuelle_pruefung_datum"] = _date_iso(latest.datum)
        row["aktuelle_pruefung_art"] = latest.art

    # denormalize: worst damage component ratings
    row["max_s"] = max((s.s for s in bridge.schaeden if s.s is not None), default=None)
    row["max_v"] = max((s.v for s in bridge.schaeden if s.v is not None), default=None)
    row["max_d"] = max((s.d for s in bridge.schaeden if s.d is not None), default=None)

    # enrichment results
    row["priority_score"] = priority_score
    row["priority_breakdown"] = priority_breakdown
    row["geschaetzte_kosten_eur"] = priority_breakdown.get("cost_estimate", {}).get("est_cost_eur")
    row["benoetigte_leistungsbereiche"] = benoetigte_leistungsbereiche
    row["intelligent_summary"] = _summary_dict(intelligent_summary)

    # provenance
    row["source_pdf_storage_path"] = pdf_storage_path
    row["source_pdf_filename"] = pdf_filename
    row["source_job_id"] = job_id
    row["extracted_at"] = _now_iso()
    row["updated_at"] = _now_iso()
    return row


def build_pruefung_row(bridge_id: str, p) -> dict:
    return {
        "bridge_id": bridge_id, "art": p.art, "datum": _date_iso(p.datum),
        "zustandsnote": p.zustandsnote,
        "zyklus_monate": p.zyklus_monate,
    }


def build_schaden_row(bridge_id: str, s, foto_storage_path: str | None) -> dict:
    return {
        "bridge_id": bridge_id, "schaden_nr": s.schaden_nr, "bsp_id": s.bsp_id,
        "bauteil": s.bauteil, "beschreibung": s.beschreibung, "ort": s.ort,
        "s": s.s, "v": s.v, "d": s.d,
        "foto_id": s.foto_key, "foto_storage_path": foto_storage_path,
    }


def build_empfehlung_row(bridge_id: str, e) -> dict:
    return {
        "bridge_id": bridge_id, "nr": e.nr,
        "art_der_leistung": e.art_der_leistung, "dringlichkeit": e.dringlichkeit,
        "geschaetzte_kosten_eur": e.geschaetzte_kosten_eur,
        "ausfuehrungsjahr": e.ausfuehrungsjahr, "bemerkung": e.bemerkung,
        "zugeordnete_schaeden": e.zugeordnete_schaeden or [],
    }


# ── orchestration ───────────────────────────────────────────────────────────
def _upsert_bridge(client, row: dict) -> str:
    resp = client.table("bridges").upsert(row, on_conflict="bauwerksnummer").execute()
    if resp.data:
        return resp.data[0]["id"]
    got = (client.table("bridges").select("id")
           .eq("bauwerksnummer", row["bauwerksnummer"]).single().execute())
    return got.data["id"]


def persist(
    bridge: BridgeExtraction,
    images: list[ExtractedImage],
    *,
    coords: tuple[float, float] | None,
    coord_source: str | None = None,
    priority_score: float,
    priority_breakdown: dict,
    benoetigte_leistungsbereiche: list[str],
    intelligent_summary,
    pdf_path: Path | str,
    job_id: str | None = None,
) -> str:
    """Persist one bridge end-to-end. Returns the bridge_id. Idempotent."""
    client = get_client()
    bwnr = _normalize_bwnr(bridge.bauwerksnummer)   # canonical key for storage + upsert
    pdf_filename = Path(pdf_path).name

    # 1. PDF to storage
    pdf_storage_path = storage.upload_pdf(client, bwnr, pdf_path)

    # 2. upsert bridge → bridge_id
    bridge_row = build_bridge_row(
        bridge, coords=coords, coord_source=coord_source, priority_score=priority_score,
        priority_breakdown=priority_breakdown,
        benoetigte_leistungsbereiche=benoetigte_leistungsbereiche,
        intelligent_summary=intelligent_summary,
        pdf_storage_path=pdf_storage_path, pdf_filename=pdf_filename, job_id=job_id,
    )
    bridge_id = _upsert_bridge(client, bridge_row)

    # 3. replace children (delete then insert)
    for table in ("pruefungen", "schaeden", "empfehlungen"):
        client.table(table).delete().eq("bridge_id", bridge_id).execute()

    # 4. photos → storage, then build schaeden rows with their paths
    schaeden_rows = []
    for s in bridge.schaeden:
        foto_path = None
        if s.foto_key and s.foto_index is not None and 0 <= s.foto_index < len(images):
            try:
                foto_path = storage.upload_photo(client, bwnr, s.foto_key, images[s.foto_index])
            except Exception as exc:  # graceful: keep the damage, drop only the photo link
                log.warning("photo upload failed for %s/%s: %s", bwnr, s.foto_key, exc)
        schaeden_rows.append(build_schaden_row(bridge_id, s, foto_path))

    # 5. insert children
    pruef_rows = [build_pruefung_row(bridge_id, p) for p in bridge.pruefungen]
    empf_rows = [build_empfehlung_row(bridge_id, e) for e in bridge.empfehlungen]
    if pruef_rows:
        client.table("pruefungen").insert(pruef_rows).execute()
    if schaeden_rows:
        client.table("schaeden").insert(schaeden_rows).execute()
    if empf_rows:
        client.table("empfehlungen").insert(empf_rows).execute()

    return bridge_id
