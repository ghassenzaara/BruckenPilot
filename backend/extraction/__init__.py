"""Phase 4 — LLM structured extraction.

One multimodal Gemini call per PDF: full page-tagged text + section 7.4 photos.
The LLM extracts structured bridge data AND assigns foto_key/foto_index per
damage, solving the photo↔damage matching problem in one shot.
"""
