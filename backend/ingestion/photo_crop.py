"""Photo-region cropping for scanned PDFs — DocLayout-YOLO.

On a digital PDF, `pdf_photos.extract_images` pulls the embedded photo objects.
On a **scanned** PDF there are no such objects: each page is one flat raster, so
embedded extraction would return whole pages, not the individual inspection
photos. This module renders each section-7.4 page and uses a document-layout
model to detect the `figure` regions, crops each one, and returns them as
`ExtractedImage` objects — the **exact same contract** `pdf_photos` produces.

That contract is the whole point: the multimodal Gemini call labels the list by
position (`[Photo index i]`), matches each damage to a photo by content, and
persistence re-fetches `images[foto_index]`. None of that cares how the bytes
were produced, so cropped scan-photos flow through the existing pipeline with no
downstream changes.

Crops are sorted top-to-bottom, then left-to-right per page, giving Gemini a
natural, reproducible photo-index order (better than the arbitrary resource
order PyMuPDF yields for digital PDFs).

The model (torch) is imported lazily and the weights download on first use, so
importing this module is cheap and digital-only runs never pay for it.
"""
import io
from functools import lru_cache
from pathlib import Path
from typing import Callable

import fitz  # PyMuPDF — page rendering
from PIL import Image

from backend import config
from backend.ingestion.pdf_photos import ExtractedImage

# DocLayout-YOLO (DocStructBench) class name for pictures/photographs. Compared
# case-insensitively; the caption class ('figure_caption') is deliberately
# excluded so we crop the photo, not its caption line.
_FIGURE_LABEL = "figure"


@lru_cache(maxsize=1)
def _model():
    """Load DocLayout-YOLO once (weights cached by huggingface_hub)."""
    try:
        from doclayout_yolo import YOLOv10
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError(
            "DocLayout-YOLO is not installed. Run "
            "`pip install doclayout-yolo huggingface_hub` (this pulls torch) "
            "to enable photo cropping for scanned PDFs."
        ) from exc

    weights = hf_hub_download(
        repo_id=config.DOCLAYOUT_REPO, filename=config.DOCLAYOUT_FILE)
    return YOLOv10(weights)


def extract_cropped_images(
    pdf_path: Path | str,
    page_range: tuple[int, int] | None = None,
    *,
    dpi: int | None = None,
    on_page: Callable[[int, int], None] | None = None,
) -> list[ExtractedImage]:
    """Detect and crop inspection photos from a scanned PDF's section-7.4 pages.

    Args:
        pdf_path:   path to the scanned PDF.
        page_range: 1-based inclusive (start, end) from `find_section_range`.
                    When None (section not found even after OCR) the whole
                    document is scanned — correct but slower and noisier.
        dpi:        render resolution; defaults to config.OCR_DPI (300).
        on_page:    optional progress callback `(page_no, last_page)`.

    Returns:
        ExtractedImage list in (page, top, left) order — same contract as
        `pdf_photos.extract_images`, so the rest of the pipeline is unchanged.
    """
    dpi = dpi or config.OCR_DPI
    model = _model()
    scale = dpi / 72.0  # rendered px → PDF points, so bbox matches digital path

    raw: list[tuple[int, tuple, Image.Image]] = []   # (page_no, bbox_pts, PIL crop)
    doc = fitz.open(pdf_path)
    try:
        first = (page_range[0] - 1) if page_range else 0      # 0-based inclusive
        last = page_range[1] if page_range else doc.page_count  # 0-based exclusive

        for page_index in range(first, min(last, doc.page_count)):
            page_no = page_index + 1
            pix = doc[page_index].get_pixmap(dpi=dpi)
            page_img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")

            boxes = _figure_boxes(model, page_img)
            # top-to-bottom (banded so near-aligned photos read left-to-right),
            # then left-to-right → natural, reproducible photo-index order.
            boxes.sort(key=lambda b: (round(b[1] / 20), b[0]))

            for (x0, y0, x1, y1) in boxes:
                crop = page_img.crop((x0, y0, x1, y1)).copy()
                bbox = (x0 / scale, y0 / scale, x1 / scale, y1 / scale)
                raw.append((page_no, bbox, crop))

            if on_page:
                on_page(page_no, min(last, doc.page_count))
    finally:
        doc.close()

    return _encode_to_budget(raw)


def _encode_to_budget(raw: list[tuple[int, tuple, Image.Image]]) -> list[ExtractedImage]:
    """Downscale + JPEG every crop, shrinking uniformly until the total payload
    fits CROP_PAYLOAD_BUDGET_MB. The DO request-body limit is ~4 MB; 300-dpi PNGs
    of a whole section can be ~30 MB. Vision models downscale internally, so this
    costs no perceived detail.
    """
    budget = config.CROP_PAYLOAD_BUDGET_MB * 1_000_000
    edge = config.CROP_MAX_EDGE

    while True:
        out: list[ExtractedImage] = []
        total = 0
        for page_no, bbox, crop in raw:
            img = crop.copy()
            if max(img.size) > edge:
                img.thumbnail((edge, edge))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=config.CROP_JPEG_QUALITY)
            data = buf.getvalue()
            total += len(data)
            out.append(ExtractedImage(
                page_no=page_no, xref=-1, width=img.width, height=img.height,
                ext="jpeg", image_bytes=data, bbox=bbox,
            ))
        if total <= budget or edge <= 384:   # fits, or hit the quality floor
            return out
        edge = int(edge * 0.8)                # shrink everything and re-encode


def _figure_boxes(model, image: Image.Image) -> list[tuple[float, float, float, float]]:
    """Return pixel (x0, y0, x1, y1) boxes for every detected figure region."""
    result = model.predict(image, conf=config.CROP_CONF, verbose=False)[0]
    names = result.names  # class index → label
    boxes: list[tuple[float, float, float, float]] = []
    for box in result.boxes:
        if names[int(box.cls)].lower() == _FIGURE_LABEL:
            x0, y0, x1, y1 = (float(v) for v in box.xyxy[0])
            boxes.append((x0, y0, x1, y1))
    return boxes
