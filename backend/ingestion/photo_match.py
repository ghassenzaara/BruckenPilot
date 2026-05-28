"""Phase 4b — deterministic photo↔damage matching. No LLM, no pixel heuristics.

In a DIN 1076 Bauwerksbuch, section 7.4 prints each inspection photo directly
ABOVE its caption, and the damage block carries a `Bild:` reference whose tokens
also appear in that caption. Both facts are exact and machine-readable, so we
bind photo→damage with zero guesswork. Each damage's `bild_ref` (the Bild: value
the LLM copied verbatim) is matched against the caption read just below each
photo's bbox, clipped to the photo's x-span so a two-column layout doesn't bleed
the neighbour in. A damage with no caption match keeps foto_index None (honest:
we found no photo rather than guessing one).

Two backends share that idea but differ in how the caption is read and scored:

  `assign()`         — TEXT-LAYER PDFs. Caption read from pdfplumber word boxes.
                       The Bild: ref is the title's prefix ("PFEILER" ⊂ "PFEILER
                       FEHLSTELLE"), so we match by longest common LEADING-token
                       prefix. Verified 3/3 on Loopetal p76–77.

  `assign_scanned()` — SCANS (no text layer). Caption read by OCR-ing the page
                       and taking the word boxes below the photo. Here the Bild:
                       ref is a unique ID ("ID069_2025_EP_0081") that reappears
                       in the caption, but OCR noise garbles the leading letters
                       ("ID"→"1D"), so leading-prefix fails. Instead we score by
                       IDF-weighted shared tokens and require a shared token that
                       is UNIQUE to one photo's caption (df==1) — which keys on
                       the discriminating number and ignores boilerplate (EP,
                       2025). Verified on Alpebachtal's section 7.4.
"""
import logging
import math
import re
from collections import Counter

import pdfplumber

from backend.extraction.llm_extract import _slug_foto_key
from backend.ingestion.pdf_photos import ExtractedImage

log = logging.getLogger(__name__)

# How far below a photo's bottom edge to look for its caption, and how much
# horizontal slack to allow when clipping to the photo's column. Points.
_CAPTION_BAND_PT = 55
_X_PAD = 6
_LINE_TOL = 4   # words within this many points of `top` are the same line


def _tokens(text: str) -> list[str]:
    """Normalize to comparable tokens: uppercase, keep only [A-Z0-9] runs.

    This drops punctuation, the "Bild:" colon, and encoding-mangled glyphs
    (pdfplumber renders some chars as U+FFFD), so 'F�' on both sides
    collapses to 'F' and still matches."""
    out, cur = [], []
    for ch in text.upper():
        if ch.isalnum() and ch.isascii():
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def _prefix_len(caption_tokens: list[str], ref_tokens: list[str]) -> int:
    """Length of the shared leading run. The Bild: ref is the title's prefix
    ('PFEILER' ⊂ 'PFEILER FEHLSTELLE'), so a real match shares token 0 onward."""
    n = 0
    for a, b in zip(caption_tokens, ref_tokens):
        if a != b:
            break
        n += 1
    return n


def _caption_title(words: list[dict], bbox: tuple) -> str:
    """The uppercase title line(s) directly below `bbox`.

    Takes words in the band under the photo, clipped to its x-span, ordered
    top-then-left, and keeps the leading run of UPPERCASE tokens — stopping at
    the first token that is lower/mixed-case (the next damage's prose) or a
    structured marker ('[67]', 'S=0', 'BSP-ID'). That isolates the title from
    everything the band would otherwise sweep up."""
    x0, _y0, x1, y1 = bbox[0], bbox[1], bbox[2], bbox[3]
    band = [
        w for w in words
        if y1 - 2 <= w["top"] <= y1 + _CAPTION_BAND_PT
        and w["x1"] >= x0 - _X_PAD and w["x0"] <= x1 + _X_PAD
    ]
    band.sort(key=lambda w: (round(w["top"] / _LINE_TOL), w["x0"]))

    title: list[str] = []
    for w in band:
        t = w["text"]
        if not t:
            continue
        if t[0] == "[" or t.startswith(("S=", "V=", "D=")) or t == "BSP-ID":
            break
        if any(c.islower() for c in t):   # entered the next damage's prose
            break
        title.append(t)
    return " ".join(title)


def _unique_key(bild_ref: str, used: set[str]) -> str:
    """A Storage-safe, per-bridge-unique foto_key derived from the Bild: text."""
    base = _slug_foto_key(bild_ref)
    key = base
    i = 2
    while key in used:
        key = f"{base}_{i}"
        i += 1
    used.add(key)
    return key


def assign(schaeden: list, images: list[ExtractedImage], pdf_path) -> int:
    """Resolve foto_index/foto_key on each damage from its bild_ref. Mutates
    `schaeden` in place; returns the number of damages matched to a photo.

    Idempotent and side-effect-free beyond the schaeden objects: it clears any
    pre-existing foto link first, so only deterministic matches survive."""
    for s in schaeden:
        s.foto_index = None
        s.foto_key = None

    refs = [(i, s) for i, s in enumerate(schaeden) if getattr(s, "bild_ref", None)]
    placed_photos = [img for img in images if img.bbox]
    if not refs or not placed_photos:
        return 0

    # caption per image index (only photos that carry a bbox + readable title)
    pages_needed = {img.page_no for img in placed_photos}
    captions: dict[int, list[str]] = {}
    with pdfplumber.open(pdf_path) as pdf:
        words_by_page = {
            p: pdf.pages[p - 1].extract_words()
            for p in pages_needed if 1 <= p <= len(pdf.pages)
        }
    for idx, img in enumerate(images):
        if img.bbox is None:
            continue
        title = _caption_title(words_by_page.get(img.page_no, []), img.bbox)
        toks = _tokens(title)
        if toks:
            captions[idx] = toks

    # score every (damage, photo) pair; assign 1:1, strongest match first
    cands: list[tuple[int, int, int, int]] = []   # (score, ref_len, di, img_idx)
    for di, s in refs:
        ref = _tokens(s.bild_ref)
        if not ref:
            continue
        for img_idx, cap in captions.items():
            score = _prefix_len(cap, ref)
            if score >= 1:
                cands.append((score, len(ref), di, img_idx))
    cands.sort(reverse=True)

    used_keys: set[str] = set()
    taken_d, taken_img = set(), set()
    matched = 0
    for _score, _rlen, di, img_idx in cands:
        if di in taken_d or img_idx in taken_img:
            continue
        s = schaeden[di]
        s.foto_index = img_idx
        s.foto_key = _unique_key(s.bild_ref, used_keys)
        taken_d.add(di)
        taken_img.add(img_idx)
        matched += 1

    log.info("photo_match: %d/%d damages with Bild: matched to a photo",
             matched, len(refs))
    return matched


# ── scan backend (OCR captions + IDF-weighted shared-token match) ────────────
_SCAN_CAPTION_BAND_PT = 26   # caption sits just below the photo (~2 OCR lines)
_OCR_MIN_CONF = 0            # keep faint digits; page constraint + df==1 gate filter noise


def _scan_tokens(text: str) -> list[str]:
    """Tokens for the OCR/ID world. In addition to the alnum runs `_tokens`
    gives, emit every standalone digit-run (≥2 digits). That is what makes the
    match survive OCR noise: a Bild ref 'ID069_2025_EP_0081' and a garbled
    caption '1D069_2025_EP' share neither 'ID069' nor 'EP_0081', but BOTH yield
    the digit-run '069' (the ID's own number, read cleanly right after the
    letters). So the ID number becomes a second discriminator independent of the
    fragile trailing number."""
    return _tokens(text) + re.findall(r"\d{2,}", text)


def _band_tokens(words: list[tuple], bbox: tuple, band_bottom: float) -> list[str]:
    """All tokens in the band below `bbox`, clipped to its x-span and stopping at
    `band_bottom` (the next photo's top — so a photo's band never reads the next
    photo's caption). Scans keep the whole caption line (the ID can sit among
    S=/V=/BSP-ID tokens); matching relies on token uniqueness, not position.
    `words` are (x0, y0, x1, y1, text) tuples in PDF points."""
    x0, _y0, x1, y1 = bbox[0], bbox[1], bbox[2], bbox[3]
    toks: list[str] = []
    for wx0, wy0, wx1, _wy1, text in words:
        if y1 - 2 <= wy0 <= band_bottom and wx1 >= x0 - _X_PAD and wx0 <= x1 + _X_PAD:
            toks.extend(_scan_tokens(text))
    return toks


def _band_bottom(images: list[ExtractedImage], idx: int) -> float:
    """Lower edge for image[idx]'s caption band: min(fixed band, top of the
    nearest photo below it in the same column). Stops the band before the next
    photo's caption so each ID lands in exactly one caption (df==1 stays true)."""
    x0, _y0, x1, y1 = images[idx].bbox
    limit = y1 + _SCAN_CAPTION_BAND_PT
    for j, im in enumerate(images):
        if j == idx or im.bbox is None or im.page_no != images[idx].page_no:
            continue
        jx0, jy0, jx1, _jy1 = im.bbox
        if jy0 >= y1 - 2 and min(x1, jx1) > max(x0, jx0):   # below + same column
            limit = min(limit, jy0 - 2)
    return limit


def _ocr_words_by_page(pdf_path, pages: list[int], dpi: int) -> dict[int, list[tuple]]:
    """OCR the given pages and return word boxes in PDF points, keyed by page.

    Heavy deps (fitz/PIL/pytesseract) are imported lazily so this module stays
    cheap to import for the text-layer path."""
    import io

    import fitz
    import pytesseract
    from PIL import Image

    from backend import config

    if config.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD

    scale = dpi / 72.0
    out: dict[int, list[tuple]] = {}
    doc = fitz.open(pdf_path)
    try:
        for pno in pages:
            if not (1 <= pno <= doc.page_count):
                continue
            pix = doc[pno - 1].get_pixmap(dpi=dpi)
            pil = Image.open(io.BytesIO(pix.tobytes("png")))
            d = pytesseract.image_to_data(
                pil, lang=config.OCR_LANG, output_type=pytesseract.Output.DICT)
            words: list[tuple] = []
            for i in range(len(d["text"])):
                t = d["text"][i].strip()
                if not t or int(d["conf"][i]) < _OCR_MIN_CONF:
                    continue
                x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
                words.append((x / scale, y / scale, (x + w) / scale, (y + h) / scale, t))
            out[pno] = words
    finally:
        doc.close()
    return out


def _locate_ref_page(bild_ref: str, page_text: list[str]) -> int | None:
    """The 1-based page whose OCR text contains this Bild: reference, else None.
    A damage and its photo are co-located on one page, so this lets us reject
    cross-page matches (where the true caption failed OCR and a number on a
    neighbouring page coincidentally collided)."""
    key = "".join(re.findall(r"[A-Za-z0-9]+", bild_ref)).upper()
    if len(key) < 6:                       # too short to locate reliably
        return None
    for i, text in enumerate(page_text):
        if key in "".join(re.findall(r"[A-Za-z0-9]+", text)).upper():
            return i + 1
    return None


def assign_scanned(schaeden: list, images: list[ExtractedImage], pdf_path,
                   *, dpi: int = 200, page_text: list[str] | None = None) -> int:
    """Scan variant of assign(): read photo captions by OCR and match each
    damage's bild_ref by IDF-weighted shared tokens. Mutates `schaeden`; returns
    the number matched. Used for PDFs with no text layer (the page is rasterized
    but the photos are recoverable and their captions are OCR-readable).

    When `page_text` (the OCR'd per-page text) is given, candidates are
    constrained to each ref's own page — a ref and its photo are always on the
    same page, so this removes cross-page false matches."""
    for s in schaeden:
        s.foto_index = None
        s.foto_key = None

    refs = [(i, s) for i, s in enumerate(schaeden) if getattr(s, "bild_ref", None)]
    placed = [img for img in images if img.bbox]
    if not refs or not placed:
        return 0

    ref_page = {}
    if page_text:
        for di, s in refs:
            ref_page[di] = _locate_ref_page(s.bild_ref, page_text)

    pages = sorted({img.page_no for img in placed})
    words_by_page = _ocr_words_by_page(pdf_path, pages, dpi)

    captions: dict[int, list[str]] = {}
    for idx, img in enumerate(images):
        if img.bbox is None:
            continue
        toks = _band_tokens(words_by_page.get(img.page_no, []), img.bbox,
                            _band_bottom(images, idx))
        if toks:
            captions[idx] = toks

    if not captions:
        return 0

    # document frequency over captions → which tokens identify a single photo,
    # and an IDF weight so boilerplate ('EP', '2025') counts for almost nothing.
    df: Counter = Counter()
    for toks in captions.values():
        df.update(set(toks))
    n = len(captions)
    idf = {t: math.log(1 + n / c) for t, c in df.items()}
    unique_tokens = {t for t, c in df.items() if c == 1}   # df==1 → discriminating

    # candidates: a damage may bind a photo only if they share a token UNIQUE to
    # that caption (keys on the ID's number, never on 'EP'/'2025'). Rank by IDF.
    cands: list[tuple[float, int, int, int]] = []
    for di, s in refs:
        ref = set(_scan_tokens(s.bild_ref))
        if not ref:
            continue
        rp = ref_page.get(di)
        for img_idx, cap in captions.items():
            if rp is not None and images[img_idx].page_no != rp:
                continue                       # ref and photo must share a page
            cap_set = set(cap)
            shared = ref & cap_set
            if not shared or not (shared & unique_tokens & cap_set):
                continue
            score = sum(idf.get(t, 0.0) for t in shared)
            cands.append((score, len(ref), di, img_idx))
    cands.sort(reverse=True)

    used_keys: set[str] = set()
    taken_d, taken_img = set(), set()
    matched = 0
    for _score, _rlen, di, img_idx in cands:
        if di in taken_d or img_idx in taken_img:
            continue
        s = schaeden[di]
        s.foto_index = img_idx
        s.foto_key = _unique_key(s.bild_ref, used_keys)
        taken_d.add(di)
        taken_img.add(img_idx)
        matched += 1

    log.info("photo_match(scan): %d/%d damages with Bild: matched to a photo",
             matched, len(refs))
    return matched
