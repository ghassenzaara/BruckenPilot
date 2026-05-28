"""Phase 5d — intelligent summary (Gemini call 2).

Feeds the now-structured + scored bridge (and, optionally, the most severe
damage photos) to Gemini and gets back exactly three prose sections. Stored as
the bridge's `intelligent_summary` JSONB.

Photos are passed by reusing the foto_index the extraction call already assigned,
so the model can describe what it sees rather than just paraphrasing text.
"""
import json

from google import genai
from google.genai import types
from pydantic import BaseModel

from backend import config
from backend.extraction.schemas import BridgeExtraction
from backend.ingestion.pdf_photos import ExtractedImage

# How many of the worst damages to attach photos for (keeps the call cheap).
_MAX_SUMMARY_PHOTOS = 4


class IntelligentSummary(BaseModel):
    situation: str      # what state the bridge is in, plainly
    risiken: str        # the concrete risks if nothing is done
    empfehlung: str     # recommended action & urgency


_PROMPT = """\
Du bist ein erfahrener Bauwerksprüfer. Auf Basis der strukturierten Daten und
(falls vorhanden) der Fotos der schwersten Schäden, fasse den Zustand des
Bauwerks für die zuständige Straßenbaubehörde zusammen.

Gib GENAU drei Abschnitte als JSON zurück:
- situation:  Der aktuelle Zustand des Bauwerks, sachlich und konkret.
- risiken:    Die konkreten Risiken, wenn nicht gehandelt wird.
- empfehlung: Die empfohlene Maßnahme und ihre Dringlichkeit.

WICHTIG — Länge: Halte jeden Abschnitt KURZ und prägnant, HÖCHSTENS 2 Sätze.
Keine Wiederholungen, keine Einleitung. Schreibe auf Deutsch, ohne Aufzählungszeichen.
Nenne KEINE konkreten Firmen — die Auftragnehmerauswahl erfolgt separat.
"""


def _severity(s) -> int:
    return (s.s or 0) * 100 + (s.v or 0) * 10 + (s.d or 0)


def summarize(
    bridge: BridgeExtraction,
    priority_breakdown: dict,
    images: list[ExtractedImage] | None = None,
) -> IntelligentSummary:
    """Run the summary call. `images` is the Phase-3 photo list (for foto_index)."""
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    payload = {
        "stammdaten": {
            "name": bridge.name, "ort": bridge.ort, "strasse": bridge.strasse,
            "baujahr": bridge.baujahr_ueberbau, "bauwerksart": bridge.bauwerksart,
            "hauptbaustoff": bridge.hauptbaustoff,
        },
        "schaeden": [
            {"nr": s.schaden_nr, "bauteil": s.bauteil, "beschreibung": s.beschreibung,
             "s": s.s, "v": s.v, "d": s.d}
            for s in bridge.schaeden
        ],
        "priority_breakdown": priority_breakdown,
    }

    parts: list = [
        types.Part.from_text(text=_PROMPT),
        types.Part.from_text(text="\n\nDATEN:\n" + json.dumps(payload, ensure_ascii=False)),
    ]

    # Attach photos for the most severe damages that have one.
    if images:
        worst = sorted(
            (s for s in bridge.schaeden if s.foto_index is not None),
            key=_severity, reverse=True,
        )[:_MAX_SUMMARY_PHOTOS]
        if worst:
            parts.append(types.Part.from_text(text="\n\nFOTOS DER SCHWERSTEN SCHÄDEN:\n"))
            for s in worst:
                if 0 <= s.foto_index < len(images):
                    img = images[s.foto_index]
                    mime = "image/jpeg" if img.ext.lower() in ("jpg", "jpeg") else f"image/{img.ext.lower()}"
                    parts.append(types.Part.from_text(text=f"\n[Schaden {s.schaden_nr}: {s.bauteil}]\n"))
                    parts.append(types.Part.from_bytes(data=img.image_bytes, mime_type=mime))

    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=IntelligentSummary,
            temperature=0.3,    # prose, not data — a little warmth is fine
        ),
    )
    return IntelligentSummary.model_validate(json.loads(response.text))
