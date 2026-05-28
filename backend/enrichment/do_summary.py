"""DO intelligent summary (OpenAI-compatible) — Gemini `summary.summarize()` twin.

Same 3-section `IntelligentSummary`, same prompt and worst-damage photos, but via
the DigitalOcean endpoint. Reuses summary.py's prompt/model/constants so both
providers return the identical shape; reuses do_extract's transport helpers.
"""
import json

from backend import config
from backend.enrichment.summary import (
    IntelligentSummary,
    _MAX_SUMMARY_PHOTOS,
    _PROMPT,
    _severity,
)
from backend.extraction.do_extract import _chat, data_uri, parse_json
from backend.extraction.schemas import BridgeExtraction
from backend.ingestion.pdf_photos import ExtractedImage


def _as_text(value) -> str:
    """Coerce a field to a plain string. Open models sometimes nest it as a dict
    (e.g. {'title': 'Situation', 'text': '…'}) instead of returning a string."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        strings = [v for v in value.values() if isinstance(v, str)]
        return max(strings, key=len) if strings else ""
    return "" if value is None else str(value)


def summarize(
    bridge: BridgeExtraction,
    priority_breakdown: dict,
    images: list[ExtractedImage] | None = None,
    *,
    model: str | None = None,
) -> IntelligentSummary:
    """Run the summary call on a DO model. Returns an IntelligentSummary."""
    model = model or config.LLM_MODEL

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
    system = (
        _PROMPT
        + '\n\nGib AUSSCHLIESSLICH dieses JSON zurück — die drei Werte sind reine '
        'Strings (KEINE verschachtelten Objekte, kein Markdown):\n'
        '{"situation": "<Text>", "risiken": "<Text>", "empfehlung": "<Text>"}'
    )

    user_content: list[dict] = [
        {"type": "text", "text": "DATEN:\n" + json.dumps(payload, ensure_ascii=False)},
    ]
    if images:
        worst = sorted(
            (s for s in bridge.schaeden if s.foto_index is not None),
            key=_severity, reverse=True,
        )[:_MAX_SUMMARY_PHOTOS]
        if worst:
            user_content.append({"type": "text", "text": "\n\nFOTOS DER SCHWERSTEN SCHÄDEN:\n"})
            for s in worst:
                if 0 <= s.foto_index < len(images):
                    user_content.append({"type": "text", "text": f"\n[Schaden {s.schaden_nr}: {s.bauteil}]\n"})
                    user_content.append({"type": "image_url", "image_url": {"url": data_uri(images[s.foto_index])}})

    content, _ = _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
        model, max_tokens=1500,
    )
    d = parse_json(content)
    return IntelligentSummary(
        situation=_as_text(d.get("situation")),
        risiken=_as_text(d.get("risiken")),
        empfehlung=_as_text(d.get("empfehlung")),
    )
