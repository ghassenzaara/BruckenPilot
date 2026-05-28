"""OCR fallback for image-only (scanned) PDFs — Tesseract, German.

When `pdf_text.looks_scanned()` is true the PDF has no usable text layer, so
nothing downstream (section finding, the LLM call) has anything to work with.
This module renders each page to an image and runs Tesseract to reconstruct a
per-page text list with the **same shape** as `pdf_text.extract_pages()`
(`list[str]`, index 0 == page 1). The pipeline can therefore swap the OCR'd
pages in and continue unchanged — `find_section_range`, `pages_to_text` and the
Gemini call all keep working.

German (`deu`) is the default language because these are DIN 1076 documents;
Tesseract gives the best German-alphabet accuracy (ä/ö/ü/ß). It is offline and
uses no Gemini quota — the right place to spend (free) local compute.
"""
import io
from pathlib import Path
from typing import Callable

import fitz  # PyMuPDF — page rendering
import pytesseract
from PIL import Image

from backend import config

# pytesseract finds the binary on PATH by default; on Windows it usually isn't,
# so honour an explicit path from config when given.
if config.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD


def _page_to_image(page, dpi: int) -> Image.Image:
    """Render one PDF page to a PIL image at the requested DPI."""
    pix = page.get_pixmap(dpi=dpi)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def ocr_pages(
    pdf_path: Path | str,
    *,
    lang: str | None = None,
    dpi: int | None = None,
    on_page: Callable[[int, int], None] | None = None,
) -> list[str]:
    """OCR every page of `pdf_path`. Returns per-page text (index 0 == page 1).

    Args:
        pdf_path: path to the scanned PDF.
        lang:     Tesseract language(s); defaults to config.OCR_LANG ('deu').
        dpi:      render resolution; defaults to config.OCR_DPI (300).
        on_page:  optional progress callback `(page_no, total_pages)`.

    Raises:
        RuntimeError: if the Tesseract binary or language data is unavailable.
    """
    lang = lang or config.OCR_LANG
    dpi = dpi or config.OCR_DPI
    _ensure_tesseract(lang)

    out: list[str] = []
    doc = fitz.open(pdf_path)
    try:
        total = doc.page_count
        for i in range(total):
            image = _page_to_image(doc[i], dpi)
            out.append(pytesseract.image_to_string(image, lang=lang))
            if on_page:
                on_page(i + 1, total)
    finally:
        doc.close()
    return out


def _ensure_tesseract(lang: str) -> None:
    """Fail early with an actionable message if Tesseract isn't usable."""
    try:
        pytesseract.get_tesseract_version()
    except Exception as exc:  # EnvironmentError / TesseractNotFoundError
        raise RuntimeError(
            "Tesseract OCR binary not found. Install it (Windows: the UB "
            "Mannheim build) including the German 'deu' language data, then "
            "add it to PATH or set TESSERACT_CMD in .env to the full path of "
            "tesseract.exe."
        ) from exc

    installed = set(pytesseract.get_languages(config=""))
    missing = [code for code in lang.split("+") if code not in installed]
    if missing:
        raise RuntimeError(
            f"Tesseract is installed but missing language data {missing}. "
            f"Available: {sorted(installed)}. Add the German pack ('deu') in "
            "the Tesseract installer or drop deu.traineddata into its tessdata "
            "folder."
        )
