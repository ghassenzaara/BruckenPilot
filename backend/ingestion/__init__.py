"""Phase 3 — PDF ingestion: page-tagged text + filtered embedded photos.

Deterministic for digital PDFs (no LLM, no network). Turns one PDF into:
  - extract_text(pdf)   -> page-marked string for the LLM (source linking)
  - extract_images(pdf) -> list[ExtractedImage] (logos/banners filtered out)
  - looks_scanned(pages)-> detect image-only PDFs that need the OCR fallback

Image-only scans are handled by the fallback siblings:
  - ocr.ocr_pages(pdf)            -> Tesseract (deu) text, same list[str] shape
  - photo_crop.extract_cropped_images(pdf) -> figure crops as ExtractedImage
"""
