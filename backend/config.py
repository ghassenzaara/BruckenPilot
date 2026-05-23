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

# --- Google Gemini (used from Phase 4 onward) ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

# --- Paths ---
PDF_INPUT_DIR = Path(os.environ.get("PDF_INPUT_DIR", str(PROJECT_ROOT / "input")))
CONTRACTORS_GEOCODED_JSON = PROJECT_ROOT / "contractors_geocoded.json"

# --- Storage buckets ---
BUCKET_PDFS = "bauwerksbuecher"
BUCKET_PHOTOS = "schaeden_fotos"
