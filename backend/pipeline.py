"""Phase 7 — single-PDF pipeline: wires Phases 3→6 into one call.

`run(pdf_path)` takes one Bauwerksbuch PDF and returns (bridge_id, usage),
having written the bridge + children + photos to Supabase. Each step reports
progress via an optional callback so the batch runner can mirror it into the
job's `status_message` (a live log without Realtime).

Raises on any failure; the batch runner (run_overnight.py) isolates it per PDF.
"""
from pathlib import Path
from typing import Callable

from backend import config
from backend.enrichment import coords as coords_mod
from backend.enrichment import geocode as geocode_mod
from backend.enrichment import do_summary, matching, scoring
from backend.enrichment import summary as summary_mod
from backend.extraction import do_extract, llm_extract
from backend.ingestion import ocr, pdf_photos, pdf_text, photo_crop, photo_match
from backend.persistence import upsert


class ScannedPdfError(RuntimeError):
    """Raised when a scan has no text layer AND OCR could not recover one."""


# One targeted retry when the deterministic count says the LLM dropped damages.
# Modest temperature: the retry prompt already names the missing damages (so the
# output changes even at 0); a small bump just helps it look again, while a big
# one would risk hallucinated damages in what must be a deterministic tool.
_RETRY_TEMPERATURE = 0.3


def _extract_once(text, step, *, expected_schaeden, feedback, temperature):
    """One extraction call: DigitalOcean (config.LLM_MODEL) when configured,
    Gemini when DO is unconfigured. A DO failure raises by default (so the real
    error is visible and Gemini's quota isn't silently spent) unless
    LLM_GEMINI_FALLBACK."""
    if config.DO_MODEL_ACCESS_KEY:
        try:
            return do_extract.extract(text, expected_schaeden=expected_schaeden,
                                      feedback=feedback, temperature=temperature)
        except Exception as exc:
            if not config.LLM_GEMINI_FALLBACK:
                raise
            step(f"DO-Extraktion fehlgeschlagen, Fallback Gemini ({exc})")
    return llm_extract.extract(text, expected_schaeden=expected_schaeden,
                               feedback=feedback, temperature=temperature)


def _llm_extract(text, step, expected_schaeden=None, marker_numbers=None):
    """Extraction with a self-correcting retry. The first pass pins the
    deterministic section-7.4 count (born-digital only). If it returns the wrong
    number of damages, retry ONCE — feeding back the exact missing marker numbers
    and a small temperature bump — then keep whichever pass is closest to the
    expected count (never end up worse).

    Text-only: photos are matched deterministically afterwards (photo_match)."""
    data, usage = _extract_once(text, step, expected_schaeden=expected_schaeden,
                                feedback=None, temperature=0.0)

    if not (expected_schaeden and marker_numbers) or len(data.schaeden) == expected_schaeden:
        return data, usage

    missing = llm_extract.missing_schaeden(data, marker_numbers)
    if not missing:
        return data, usage   # count off but all numbers present (e.g. duplicates) — leave it

    step(f"Nachforderung: {len(data.schaeden)}/{expected_schaeden} Schäden — "
         f"fehlen {', '.join(f'[{n}]' for n in missing)}")
    try:
        retry_data, retry_usage = _extract_once(
            text, step, expected_schaeden=expected_schaeden,
            feedback=llm_extract.retry_instruction(missing, expected_schaeden),
            temperature=_RETRY_TEMPERATURE)
    except Exception as exc:
        step(f"Nachforderung fehlgeschlagen ({exc}) — erste Extraktion wird verwendet")
        return data, usage

    if abs(len(retry_data.schaeden) - expected_schaeden) < abs(len(data.schaeden) - expected_schaeden):
        return retry_data, retry_usage
    return data, usage


def _llm_summary(data, breakdown, images, step):
    """Summary via DigitalOcean when configured; Gemini when unconfigured. DO
    failure raises by default unless LLM_GEMINI_FALLBACK (see _llm_extract)."""
    if config.DO_MODEL_ACCESS_KEY:
        try:
            return do_summary.summarize(data, breakdown, images)
        except Exception as exc:
            if not config.LLM_GEMINI_FALLBACK:
                raise
            step(f"DO-Zusammenfassung fehlgeschlagen, Fallback Gemini ({exc})")
    return summary_mod.summarize(data, breakdown, images)


def run(
    pdf_path: Path | str,
    *,
    job_id: str | None = None,
    on_step: Callable[[str], None] | None = None,
) -> tuple[str, dict]:
    """Process one PDF end-to-end. Returns (bridge_id, llm_usage_dict)."""
    def step(msg: str) -> None:
        if on_step:
            on_step(msg)

    pdf_path = Path(pdf_path)

    # 1. text (one read); OCR fallback for image-only scans
    step("Text wird extrahiert")
    pages = pdf_text.extract_pages(pdf_path)
    scanned = pdf_text.looks_scanned(pages)
    if scanned:
        # No text layer → reconstruct it with Tesseract (German). Must happen
        # before find_section_range so cropping below can scope to section 7.4
        # instead of running the layout model over the whole document.
        step("Gescanntes PDF — OCR (deu) läuft")
        pages = ocr.ocr_pages(
            pdf_path, on_page=lambda n, tot: step(f"OCR Seite {n}/{tot}")
        )
        if pdf_text.looks_scanned(pages):
            raise ScannedPdfError(
                f"{pdf_path.name}: OCR lieferte keinen verwertbaren Text"
            )
    text = pdf_text.pages_to_text(pages)

    # 2. locate the Schäden section + extract its photos
    step("Abschnitt 7.4 wird lokalisiert")
    section = pdf_text.find_section_range(pages)
    # Deterministic damage markers from section 7.4 ("[19] S=0, V=0, D=2").
    # Born-digital only — scans garble the brackets, so leave it None and let the
    # prompt rule + a soft check handle them (no hard count forced).
    marker_numbers = None if scanned else pdf_text.schaeden_marker_numbers(pages, section)
    expected_schaeden = len(marker_numbers) if marker_numbers is not None else None
    if expected_schaeden:
        step(f"{expected_schaeden} Schäden in Abschnitt 7.4 erkannt")
    step("Fotos werden extrahiert")
    if scanned:
        # A no-text-layer PDF can still carry photos as embedded objects (the
        # text is rasterized, the photos aren't — e.g. Alpebachtal). Extract those
        # directly (deterministic, no ML), filtering out rasterized-text strips by
        # size. Only a TRULY flat raster yields none → fall back to figure-cropping.
        images = pdf_photos.extract_images(
            pdf_path, page_range=section,
            min_short_side=config.SCAN_EMBEDDED_MIN_PX,
        )
        if images:
            # one photo may be stored as several stacked tiles — stitch them so
            # we keep the whole image, not a slice (one photo per damage).
            images = pdf_photos.merge_stacked_tiles(images)
            step(f"{len(images)} eingebettete Fotos gefunden")
        else:
            images = photo_crop.extract_cropped_images(
                pdf_path, page_range=section,
                on_page=lambda n, tot: step(f"Fotos werden zugeschnitten ({n}/{tot})"),
            )
    else:
        images = pdf_photos.extract_images(pdf_path, page_range=section)

    # 3. text-only LLM extraction (+ domain gate inside extract)
    step("LLM-Extraktion läuft")
    data, usage = _llm_extract(text, step, expected_schaeden, marker_numbers)
    if expected_schaeden:
        got = len(data.schaeden)
        if got == expected_schaeden:
            step(f"{got}/{expected_schaeden} Schäden extrahiert")
        else:
            step(f"Achtung: {got}/{expected_schaeden} Schäden extrahiert — Abweichung")

    # 3a. 7.6 recommendation↔damage link — re-derive DETERMINISTICALLY from the
    #     "Zugeordnete Schäden:" lists (born-digital only; the braces garble on
    #     scans, so there we keep whatever the LLM read). Filtered to the real 7.4
    #     damage ids so a stray bracket can't sneak in. Authoritative over the LLM.
    if not scanned and data.empfehlungen:
        links = pdf_text.empfehlung_links(pages, valid_schaeden=marker_numbers)
        for e in data.empfehlungen:
            if e.nr is not None and e.nr in links:
                e.zugeordnete_schaeden = links[e.nr]
        step(f"{len(data.empfehlungen)} Empfehlungen (Abschnitt 7.6) verknüpft")

    # 3b. deterministic photo↔damage matching from each damage's verbatim
    #     bild_ref + the on-page caption (no LLM, no pixel heuristics).
    #       - text PDFs: caption read from the text layer (assign).
    #       - scans:     caption read by OCR-ing the photo pages (assign_scanned),
    #                    constrained to each ref's page via the OCR'd page text.
    if images:
        step("Fotos werden den Schäden zugeordnet")
        if scanned:
            n = photo_match.assign_scanned(
                data.schaeden, images, pdf_path,
                dpi=config.OCR_DPI, page_text=pages,
            )
        else:
            n = photo_match.assign(data.schaeden, images, pdf_path)
        step(f"{n} Foto(s) zugeordnet")

    # 4. coordinates: UTM from the document → WGS84; if the doc has no UTM block
    #    (some older prints don't), geocode the address as an approximate pin.
    step("Koordinaten werden umgerechnet")
    coords = coords_mod.to_wgs84(
        data.utm_rechtswert, data.utm_hochwert, data.utm_bezugssystem
    )
    coord_source = "utm" if coords else None
    if coords is None:
        step("Keine UTM-Koordinaten — Adresse wird geokodiert")
        coords = geocode_mod.geocode_bridge(data)
        if coords:
            coord_source = "geocoded"

    # 5. priority score
    step("Priorität wird berechnet")
    priority_score, breakdown = scoring.score(data)

    # 6. contractor capability set
    step("Leistungsbereiche werden ermittelt")
    needed_lbs = matching.required_leistungsbereiche(data)

    # 7. intelligent summary (LLM call 2)
    step("Zusammenfassung wird erstellt")
    summary = _llm_summary(data, breakdown, images, step)

    # 8. persist (storage + idempotent upsert)
    step("Wird gespeichert")
    bridge_id = upsert.persist(
        data, images,
        coords=coords,
        coord_source=coord_source,
        priority_score=priority_score,
        priority_breakdown=breakdown,
        benoetigte_leistungsbereiche=needed_lbs,
        intelligent_summary=summary,
        pdf_path=pdf_path,
        job_id=job_id,
    )
    step("Fertig")
    return bridge_id, usage
