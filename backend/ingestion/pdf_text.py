"""Phase 3 — text extraction with pdfplumber. Deterministic, no LLM.

Pages are tagged with `===== PAGE n =====` markers (1-based, matching the photo
page numbers and the LLM's `source_pages` output) so the model can cite the page
a value came from — the audit-trail differentiator.
"""
import re

import pdfplumber

PAGE_MARKER = "===== PAGE {n} ====="

# Average chars/page below this means there is no usable text layer: the PDF is
# an image-only scan (e.g. Alpebachtal: ~1 char/page over 127 pages) and needs
# OCR, which is out of scope for the batch. Real text PDFs run 600–1000+/page.
MIN_CHARS_PER_PAGE = 50

# DIN 1076 section headers in the running header (top of each page).
# The TOC entries look identical but always end with a date (DD.MM.YYYY) —
# the date pattern is the reliable discriminator.
_DATE_RE = re.compile(r"\d{2}\.\d{2}\.\d{4}")
_SEC74_RE = re.compile(r"7\.4\s+Sch")     # Schäden / Schadensbilder / Sch den (encoding)
_SEC75_RE = re.compile(r"7\.5\s+\w")      # Bewertung / next subsection


def extract_pages(pdf_path) -> list[str]:
    """Per-page text, in order. Index 0 == page 1. Empty pages yield ''."""
    with pdfplumber.open(pdf_path) as pdf:
        return [(page.extract_text() or "") for page in pdf.pages]


def pages_to_text(pages: list[str]) -> str:
    """Join per-page text into one page-tagged string for the LLM."""
    blocks = [f"{PAGE_MARKER.format(n=i + 1)}\n{text}" for i, text in enumerate(pages)]
    return "\n\n".join(blocks)


def extract_text(pdf_path) -> str:
    """Whole document as one page-tagged string for the LLM."""
    return pages_to_text(extract_pages(pdf_path))


def looks_scanned(pages: list[str]) -> bool:
    """True if the PDF has effectively no text layer (image-only scan).

    The batch should fail such a job with a clear 'needs OCR' reason rather than
    feed an empty document to the LLM.
    """
    if not pages:
        return True
    total_chars = sum(len(t) for t in pages)
    return total_chars / len(pages) < MIN_CHARS_PER_PAGE


def _has_section_header(text: str, pattern: re.Pattern) -> bool:
    """True if any non-TOC line in text matches the section pattern.

    TOC entries look like "7.4 Schäden 12.01.2023" (date at end).
    Running page headers look like "7.4 Schäden" (no date).
    Footer lines look like "Seite 7.5" — the regex requires a word char after
    the section number, so "7.5" at end-of-line (footer) never matches.
    """
    for line in text.splitlines():
        if pattern.search(line) and not _DATE_RE.search(line):
            return True
    return False


def find_section_range(pages: list[str]) -> tuple[int, int] | None:
    """Return the 1-based inclusive page range for section 7.4 (Schäden).

    Scans running headers, ignoring TOC entries (have a date) and footer page
    numbers ("Seite 7.X" — not followed by a word character). Returns None if
    the section cannot be found (e.g. a scan whose 7.4 header didn't OCR).

    Two ways the end is determined:
      1. The clean case — the first page carrying the *next* section header
         (7.5) and not 7.4: section 7.4 ended on the previous page.
      2. The fallback — 7.5 is never matched. This happens on OCR'd scans where
         "7.5 Bewertung" is misread (e.g. the 5 → 3, giving "7.3 Bewertung").
         We then bound the section to the LAST page whose header still showed
         7.4, never to the end of the document — otherwise cropping/extraction
         would run from 7.4 all the way through the rest of the PDF.
    """
    start: int | None = None
    last74: int | None = None        # last page whose header still shows 7.4

    for i, text in enumerate(pages):
        page_no = i + 1
        has74 = _has_section_header(text, _SEC74_RE)
        has75 = _has_section_header(text, _SEC75_RE)

        if start is None:
            if has74 and not has75:
                start = page_no          # first real 7.4 page (not TOC)
                last74 = page_no
        else:
            if has74:
                last74 = page_no
            if has75 and not has74:
                return (start, page_no - 1)   # first 7.5-only page → section ended

    if start is None:
        return None
    return (start, last74)           # 7.5 never matched → bound to last 7.4 page


# A damage in 7.4 begins with a bracketed damage-id immediately followed by its
# S/V/D classification — "[19] S=0, V=0, D=2". Brackets containing text
# ("[Längsriss…]") are part of a description and never match. So these markers in
# the 7.4 range are the exact damage set (and their numbers), with no LLM.
_DAMAGE_MARKER_RE = re.compile(r"\[\s*(\d+)\s*\]\s*S\s*=")


def schaeden_marker_numbers(pages: list[str], section: tuple[int, int] | None) -> list[int] | None:
    """The bracketed damage numbers in section 7.4, in document order.

    `section` is the page range from `find_section_range`. Returns None when the
    section can't be located. The caller must ALSO skip this for OCR'd scans:
    Tesseract garbles the brackets, so the marker pattern is unreliable there
    (handle scans with the prompt rule + a soft check instead). Never raises.
    """
    if not section:
        return None
    start, end = section
    blob = "\n".join(pages[start - 1:end])
    return [int(n) for n in _DAMAGE_MARKER_RE.findall(blob)]


def count_schaeden(pages: list[str], section: tuple[int, int] | None) -> int | None:
    """Deterministic count of damages in section 7.4 (born-digital only).

    None when the section can't be located (see schaeden_marker_numbers)."""
    nums = schaeden_marker_numbers(pages, section)
    return None if nums is None else len(nums)


# Section 7.6 Empfehlungen: each recommendation begins with "Maßnahmenempfehlung
# {n}" and lists the damages it addresses under "Zugeordnete Schäden: [a],[b]".
# The marker token only occurs in 7.6 content (never the TOC), so we can scan the
# whole document — no fragile section-range location needed.
_EMPF_MARKER_RE = re.compile(r"Ma[ßs]+nahmenempfehlung\s*\{\s*(\d+)\s*\}")
_BRACKET_ID_RE = re.compile(r"\[\s*(\d+)\s*\]")
_ZUGEORDNET_RE = re.compile(r"Zugeordnete\s+Sch[aä]den\s*:")


def empfehlung_links(pages: list[str], valid_schaeden: list[int] | None = None) -> dict[int, list[int]]:
    """Map each 7.6 recommendation {n} → the damage numbers under its
    "Zugeordnete Schäden:" list. The authoritative damage↔recommendation link.

    Born-digital only — Tesseract garbles the braces on scans, so the caller must
    skip this for OCR'd documents (fall back to the LLM's zugeordnete_schaeden).

    Each block runs from one "Maßnahmenempfehlung {n}" marker to the next; damage
    ids are taken only from AFTER "Zugeordnete Schäden:" within the block (so a
    bracket id mentioned earlier in a Bemerkung is never miscounted). When
    `valid_schaeden` is given, ids are filtered to that set — this drops any stray
    bracket the last (unbounded) block might capture from a following section.

    Returns {nr: [ids]} (empty {} when the document has no recommendations)."""
    full = "\n".join(pages)
    markers = list(_EMPF_MARKER_RE.finditer(full))
    if not markers:
        return {}
    valid = set(valid_schaeden) if valid_schaeden is not None else None
    links: dict[int, list[int]] = {}
    for i, m in enumerate(markers):
        nr = int(m.group(1))
        end = markers[i + 1].start() if i + 1 < len(markers) else len(full)
        block = full[m.end():end]
        z = _ZUGEORDNET_RE.search(block)
        if not z:
            links.setdefault(nr, [])
            continue
        ids = [int(x) for x in _BRACKET_ID_RE.findall(block[z.end():])]
        if valid is not None:
            ids = [x for x in ids if x in valid]
        links[nr] = list(dict.fromkeys(ids))   # de-dupe, keep document order
    return links


def empfehlung_numbers(pages: list[str]) -> list[int]:
    """The {n} recommendation ids in section 7.6, in document order (born-digital
    only). Empty list when there are no recommendations ("Keine Angaben")."""
    return [int(x) for x in _EMPF_MARKER_RE.findall("\n".join(pages))]
