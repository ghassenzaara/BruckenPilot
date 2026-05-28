"""Central configuration for the BrückenPilot backend.

Reads `.env` from the project root and exposes settings plus well-known paths.
Import this module instead of touching os.environ directly.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = the directory that contains the `backend/` package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# --- Supabase (service-role key: the batch writes everything server-side) ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# --- Google Gemini (legacy LLM provider) ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

# --- DigitalOcean Gradient inference (OpenAI-compatible) -------------------
# Replaces Gemini: GPT-5 mini is vision-capable, cheaper, and not quota-capped.
# DO_MODEL_ACCESS_KEY is the model-access key created in the DO console (keep
# it in .env, never in code). Endpoint speaks the OpenAI Chat Completions API.
DO_INFERENCE_BASE_URL = os.environ.get(
    "DO_INFERENCE_BASE_URL", "https://inference.do-ai.run/v1")
DO_MODEL_ACCESS_KEY = os.environ.get("DO_MODEL_ACCESS_KEY", "")
# Big scans (long OCR text + dozens of image crops) are slow to prefill; 300s
# wasn't enough. Processing time doesn't matter here, so allow plenty.
DO_TIMEOUT_S = int(os.environ.get("DO_TIMEOUT_S", "600"))
# Vision-capable open model validated for this tier (commercial GPT/Claude are
# 403-gated). When DO_MODEL_ACCESS_KEY is set, the pipeline uses this; otherwise
# it falls back to Gemini.
LLM_MODEL = os.environ.get("LLM_MODEL", "llama-4-maverick")

# Fall back to Gemini if a DO call FAILS? Default OFF: Gemini's free tier is
# tightly capped (20/day), so a silent fallback both burns that quota and hides
# the real DO error. With this off, a DO failure raises (visible in the job).
# Set LLM_GEMINI_FALLBACK=1 to re-enable the safety net.
LLM_GEMINI_FALLBACK = os.environ.get("LLM_GEMINI_FALLBACK", "0").lower() in ("1", "true", "yes")

# --- OCR fallback for image-only (scanned) PDFs ---------------------------
# Tesseract gives the best German-alphabet accuracy but needs the binary
# installed separately. On Windows it is usually NOT on PATH, so point
# TESSERACT_CMD at the full path of tesseract.exe (UB Mannheim build).
# OCR_LANG must be installed in Tesseract ('deu' = German language data).
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "")     # "" → rely on PATH
OCR_LANG = os.environ.get("OCR_LANG", "deu")
OCR_DPI = int(os.environ.get("OCR_DPI", "300"))         # 300 dpi: good German OCR

# Some "scans" have no text layer (the text is rasterized into image strips) but
# still carry the inspection PHOTOS as embedded objects (e.g. Alpebachtal). We
# extract those directly instead of running the layout model. An embedded raster
# shorter than this on its short side is rendered text, not a photograph — the
# gap is wide (text strips ≈30–60px, photos ≈480px), so the cutoff is structural.
SCAN_EMBEDDED_MIN_PX = int(os.environ.get("SCAN_EMBEDDED_MIN_PX", "200"))

# --- Photo-region cropping for scanned PDFs (layout detection) ------------
# A truly flat scanned page has no embedded photos, so embedded extraction
# returns nothing and we fall back to DocLayout-YOLO detecting 'figure' regions.
# Weights auto-download from Hugging Face on first use.
DOCLAYOUT_REPO = os.environ.get(
    "DOCLAYOUT_REPO", "juliozhao/DocLayout-YOLO-DocStructBench")
DOCLAYOUT_FILE = os.environ.get(
    "DOCLAYOUT_FILE", "doclayout_yolo_docstructbench_imgsz1024.pt")
CROP_CONF = float(os.environ.get("CROP_CONF", "0.25"))  # min detection confidence
# Crops are rendered at OCR_DPI (300) → multi-MB PNGs. Downscale + JPEG them so
# the (often dozens of) crops fit one LLM request and aren't huge in storage.
# If the total still exceeds the budget, crops are shrunk further until they fit
# (the DO request-body limit is ~4 MB; vision models downscale internally anyway).
CROP_MAX_EDGE = int(os.environ.get("CROP_MAX_EDGE", "1024"))     # px, longest side
CROP_JPEG_QUALITY = int(os.environ.get("CROP_JPEG_QUALITY", "85"))
CROP_PAYLOAD_BUDGET_MB = float(os.environ.get("CROP_PAYLOAD_BUDGET_MB", "3.5"))

# --- Paths ---
PDF_INPUT_DIR = Path(os.environ.get("PDF_INPUT_DIR", str(PROJECT_ROOT / "input")))
CONTRACTORS_GEOCODED_JSON = PROJECT_ROOT / "contractors_geocoded.json"

# --- Storage buckets ---
BUCKET_PDFS = "bauwerksbuecher"
BUCKET_PHOTOS = "schaeden_fotos"

# --- Geocoding (address → WGS84 fallback when a doc has no UTM coordinates) ---
# Nominatim requires a real, identifying User-Agent and allows max 1 req/sec.
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
NOMINATIM_USER_AGENT = os.environ.get("NOMINATIM_USER_AGENT", "BrueckenPilot/1.0 (bridge-pipeline)")
