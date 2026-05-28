"""Dry-run extraction check — NO database writes, NO storage uploads, NO deletes.

    python -m backend.verify_extraction [PDF_DIR]

Runs the REAL extraction path (text → OCR-if-scanned → find_section_range →
deterministic Schaden count → LLM extract with the one-shot retry) on every PDF
and prints expected vs. extracted damage counts. Use this to confirm quality
BEFORE wiping the database and re-running `backend.run_overnight`.

It spends LLM inference (DigitalOcean primary) but never touches anything
persistent: no Supabase rows, no extraction_jobs, no Storage objects.
"""
import sys
from pathlib import Path

from backend import config, pipeline
from backend.ingestion import ocr, pdf_text


def verify_one(pdf: Path) -> tuple[str, bool]:
    """Return (one-line summary, ok?) for a single PDF. Writes nothing."""
    pages = pdf_text.extract_pages(pdf)
    scanned = pdf_text.looks_scanned(pages)
    if scanned:
        print("     · gescanntes PDF — OCR (deu) läuft …")
        pages = ocr.ocr_pages(pdf)
        if pdf_text.looks_scanned(pages):
            return "OCR lieferte keinen verwertbaren Text", False

    text = pdf_text.pages_to_text(pages)
    section = pdf_text.find_section_range(pages)
    marker_numbers = None if scanned else pdf_text.schaeden_marker_numbers(pages, section)
    expected = len(marker_numbers) if marker_numbers is not None else None

    # the exact pipeline path (deterministic count pinned + one retry), no persist
    data, _ = pipeline._llm_extract(text, lambda m: print(f"     · {m}"),
                                    expected, marker_numbers)
    got = len(data.schaeden)
    got_nums = sorted(s.schaden_nr for s in data.schaeden if s.schaden_nr is not None)

    if expected is None:
        print(f"   7.4={section}  scan/kein Sollwert → LLM lieferte {got} Schäden")
        print(f"   Ist {got_nums}")
        return f"{got} Schäden (Scan, kein Sollwert)", True

    ok = got == expected
    print(f"   7.4={section}  Soll {expected} / Ist {got}  [{'OK' if ok else 'ABWEICHUNG'}]")
    print(f"   Marker (Soll) {sorted(marker_numbers)}")
    print(f"   Ist           {got_nums}")
    if not ok:
        missing = [n for n in sorted(set(marker_numbers)) if n not in set(got_nums)]
        extra = [n for n in got_nums if n not in set(marker_numbers)]
        if missing:
            print(f"   fehlen        {missing}")
        if extra:
            print(f"   zu viel       {extra}")
    return f"Soll {expected} / Ist {got}  [{'OK' if ok else 'ABWEICHUNG'}]", ok


def main() -> int:
    # Force UTF-8 so the German status text never crashes a cp1252 console.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    pdf_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else config.PDF_INPUT_DIR
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    print(f"DRY RUN — keine DB-/Storage-Schreibvorgänge. "
          f"{len(pdfs)} PDF(s) in {pdf_dir}\n")
    if not pdfs:
        print("Keine PDFs gefunden. Pfad als Argument übergeben, z. B.:\n"
              "    python -m backend.verify_extraction pdfs")
        return 0

    results = []
    for pdf in pdfs:
        print(f"[>] {pdf.name}")
        try:
            summary, ok = verify_one(pdf)
        except Exception as exc:  # isolate — one bad PDF never aborts the check
            summary, ok = f"FEHLER: {type(exc).__name__}: {exc}", False
            print(f"   [FAIL] {summary}")
        results.append((pdf.name, summary, ok))
        print()

    print("=" * 64)
    print("ZUSAMMENFASSUNG (Dry Run — nichts gespeichert):")
    for name, summary, ok in results:
        print(f"  {'OK ' if ok else 'XX '} {name}: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
