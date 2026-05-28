"""Phase 3 — embedded photo extraction with PyMuPDF (fitz). Deterministic, no LLM.

Two filters, in order of importance:

1. PAGE SCOPING — only pages in the section 7.4 (Schäden) range are processed.
   DIN 1076 is a standardised format: all inspection photos live in section 7.4.
   This is structural knowledge, not a pixel heuristic, so it scales to any number
   of PDFs regardless of image dimensions or logo sizes.

2. RECURRENCE FILTER — any image whose content (SHA-1 of bytes) appears on more
   than RECUR_PAGE_MAX distinct pages is page chrome (logo, watermark, template
   diagram) and is dropped. Logos always repeat across the whole document;
   inspection photos appear once.

No hard-coded pixel thresholds. No vision model for filtering.
Photo↔damage matching does NOT happen here — it is resolved deterministically
in `photo_match.py` (Phase 4b) from each image's bbox (captured below) and the
damage's bild_ref. No LLM is involved in the match.
"""
import hashlib
import io
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

# An image whose content appears on more than this many pages is chrome.
# Inspection photos appear on exactly one page; logos repeat throughout.
RECUR_PAGE_MAX = 3


@dataclass
class ExtractedImage:
    page_no: int               # 1-based, matches pdf_text PAGE markers
    xref: int                  # PDF cross-reference id (unique per image object)
    width: int
    height: int
    ext: str                   # 'jpeg', 'png', …
    image_bytes: bytes         # original embedded bytes, not re-encoded
    bbox: tuple | None         # (x0, y0, x1, y1) on the page — for proximity matching


def extract_images(
    pdf_path: Path | str,
    page_range: tuple[int, int] | None = None,
    *,
    min_short_side: int = 0,
) -> list[ExtractedImage]:
    """Extract inspection photos from the PDF.

    Args:
        pdf_path:   path to the PDF file.
        page_range: 1-based inclusive (start, end) from `find_section_range`.
                    When None, the whole document is scanned (useful for testing,
                    but production always passes the 7.4 section range).
        min_short_side: drop any image whose shorter side (px) is below this.
                    0 (default, digital PDFs) keeps everything. Used for hybrid
                    scans to discard rasterized-text strips while keeping photos.

    Returns:
        List of ExtractedImage in (page, document) order, chrome filtered out.
    """
    candidates: list[ExtractedImage] = []
    content_hash: list[str] = []
    pages_per_hash: dict[str, set[int]] = defaultdict(set)

    doc = fitz.open(pdf_path)
    try:
        section_first = (page_range[0] - 1) if page_range else 0     # 0-based inclusive
        section_last = page_range[1] if page_range else doc.page_count  # 0-based exclusive

        # Pass 1 — whole document: count distinct pages per content hash.
        # The logo appears on every page of the full document, not just the 3
        # section pages; counting across the whole doc makes the recurrence filter
        # robust regardless of how short the section is.
        for page_index in range(doc.page_count):
            page = doc[page_index]
            seen_xrefs: set[int] = set()
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                info = doc.extract_image(xref)
                if not info:
                    continue
                digest = hashlib.sha1(info["image"]).hexdigest()
                pages_per_hash[digest].add(page_index + 1)

        # Pass 2 — section pages only: collect candidates that are not chrome.
        for page_index in range(section_first, min(section_last, doc.page_count)):
            page = doc[page_index]
            page_no = page_index + 1
            seen_xrefs = set()

            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                info = doc.extract_image(xref)
                if not info:
                    continue

                data = info["image"]
                digest = hashlib.sha1(data).hexdigest()

                if len(pages_per_hash[digest]) > RECUR_PAGE_MAX:
                    continue  # recurring chrome (logo / watermark across the whole doc)

                if min_short_side and min(info["width"], info["height"]) < min_short_side:
                    continue  # rasterized-text strip on a hybrid scan, not a photo

                rects = page.get_image_rects(xref)
                bbox = tuple(rects[0]) if rects else None

                candidates.append(ExtractedImage(
                    page_no=page_no,
                    xref=xref,
                    width=info["width"],
                    height=info["height"],
                    ext=info["ext"],
                    image_bytes=data,
                    bbox=bbox,
                ))
                content_hash.append(digest)
    finally:
        doc.close()

    return candidates


def _stitch(run: list[ExtractedImage]) -> ExtractedImage:
    """Vertically stitch a run of tiles (top→bottom) into one ExtractedImage,
    with the union bbox. Bytes are re-encoded as JPEG."""
    pils = [Image.open(io.BytesIO(t.image_bytes)).convert("RGB") for t in run]
    w = max(p.width for p in pils)
    h = sum(p.height for p in pils)
    canvas = Image.new("RGB", (w, h), "white")
    y = 0
    for p in pils:
        canvas.paste(p, (0, y))
        y += p.height
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=90)
    top, bottom = run[0], run[-1]
    bbox = (min(t.bbox[0] for t in run), top.bbox[1],
            max(t.bbox[2] for t in run), bottom.bbox[3])
    return ExtractedImage(page_no=top.page_no, xref=top.xref, width=w, height=h,
                          ext="jpeg", image_bytes=buf.getvalue(), bbox=bbox)


def merge_stacked_tiles(
    images: list[ExtractedImage],
    *, x_tol: float = 4, w_tol: float = 6, gap_tol: float = 4,
) -> list[ExtractedImage]:
    """Reassemble photos that a producer stored as several vertically-stacked
    tiles. Some scanned Bauwerksbücher slice one 4:3 photo into two touching
    1280×480 tiles (verified on Alpebachtal); persisting a single tile would
    show only half the photo. Tiles in the same column (same x0 ± x_tol), of the
    same width (± w_tol), whose edges touch (gap ≤ gap_tol pt), are stitched into
    one image. A photo stored as a single object is a run of one → unchanged.

    Operates on bbox geometry, so only meaningful for the embedded-extraction
    path (digital/hybrid PDFs); crops from the layout model are already whole."""
    by_page: dict[int, list[ExtractedImage]] = defaultdict(list)
    for im in images:
        by_page[im.page_no].append(im)

    out: list[ExtractedImage] = []
    for page_no in sorted(by_page):
        out.extend(im for im in by_page[page_no] if im.bbox is None)
        tiles = [im for im in by_page[page_no] if im.bbox is not None]
        tiles.sort(key=lambda im: (round(im.bbox[0]), im.bbox[1]))  # column, then top

        used = [False] * len(tiles)
        for i, im in enumerate(tiles):
            if used[i]:
                continue
            run = [im]
            used[i] = True
            for j in range(i + 1, len(tiles)):
                if used[j]:
                    continue
                prev, cand = run[-1], tiles[j]
                same_col = abs(cand.bbox[0] - prev.bbox[0]) <= x_tol
                same_w = abs((cand.bbox[2] - cand.bbox[0]) - (prev.bbox[2] - prev.bbox[0])) <= w_tol
                touching = abs(cand.bbox[1] - prev.bbox[3]) <= gap_tol
                if same_col and same_w and touching:
                    run.append(cand)
                    used[j] = True
            out.append(_stitch(run) if len(run) > 1 else run[0])
    return out
