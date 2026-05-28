"""Phase 6 — Supabase Storage uploads.

Deterministic object paths so a re-run overwrites instead of orphaning files:
  PDF    → bauwerksbuecher/{bauwerksnummer}.pdf
  photo  → schaeden_fotos/{bauwerksnummer}/{foto_key}.{ext}

`upsert: "true"` makes the upload overwrite an existing object (idempotency).
Returns the in-bucket object path, which is what gets stored on the DB rows and
what the frontend passes to `createSignedUrl(path)`.
"""
from pathlib import Path

from backend import config
from backend.ingestion.pdf_photos import ExtractedImage


def _mime_for(ext: str) -> str:
    e = ext.lower()
    return "image/jpeg" if e in ("jpg", "jpeg") else f"image/{e}"


def upload_pdf(client, bauwerksnummer: str, pdf_path: Path | str) -> str:
    """Upload the source PDF. Returns the object path within the PDFs bucket."""
    object_path = f"{bauwerksnummer}.pdf"
    data = Path(pdf_path).read_bytes()
    client.storage.from_(config.BUCKET_PDFS).upload(
        object_path, data,
        {"content-type": "application/pdf", "upsert": "true"},
    )
    return object_path


def upload_photo(
    client, bauwerksnummer: str, foto_key: str, image: ExtractedImage
) -> str:
    """Upload one damage photo. Returns the object path within the photos bucket."""
    object_path = f"{bauwerksnummer}/{foto_key}.{image.ext.lower()}"
    client.storage.from_(config.BUCKET_PHOTOS).upload(
        object_path, image.image_bytes,
        {"content-type": _mime_for(image.ext), "upsert": "true"},
    )
    return object_path
