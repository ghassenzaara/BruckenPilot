"""Phase 4 — text-only Gemini extraction (the DO path mirrors this).

One call per PDF: full page-tagged text in, structured BridgeExtraction out.
No images are sent. The LLM copies each damage's "Bild:" value verbatim into
`bild_ref`; the actual photo↔damage link is resolved deterministically afterwards
in ingestion.photo_match (Phase 4b) from that bild_ref + the on-page caption.

Usage:
    bridge, usage = extract(text)
    photo_match.assign(bridge.schaeden, images, pdf_path)  # sets foto_index/key
"""
import json
import logging
import re

from google import genai
from google.genai import types

from backend import config
from backend.extraction.schemas import BridgeExtraction

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Du bist ein Experte für das deutsche Bauwerksprüfungssystem (DIN 1076).
Du erhältst den vollständigen Text eines Bauwerksbuchs (mit ===== PAGE n ===== Markierungen).

Extrahiere alle Daten gemäß dem vorgegebenen JSON-Schema. Halte dich dabei an folgende Regeln:

ZAHLENFORMATE — normalisiere vor der Ausgabe:
- Dezimalkomma → Punkt: 2,2 → 2.2
- Tausenderpunkt entfernen: 1.776,57 → 1776.57
- Datum DD.MM.YYYY → ISO YYYY-MM-DD

BILD-VERWEISE (Abschnitt 7.4):
- Manche Schäden enthalten im Beschreibungstext einen "Bild:"-Verweis.
- Übernimm den Text direkt NACH "Bild:" WORTWÖRTLICH (exakter Wortlaut und
  Großschreibung wie im Dokument) in das Feld bild_ref — bis zum nächsten Feld
  bzw. Zeilenende (Stopp z. B. bei "Anzahl:", "Maßnahme", "{", neuer Schaden).
  Beispiel: "...Bild:PFEILER Anzahl: 20 Stück..." → bild_ref = "PFEILER".
- Wenn KEIN "Bild:"-Verweis vorhanden ist: bild_ref null lassen.
- Setze foto_key und foto_index NICHT — die Foto-Zuordnung erfolgt
  deterministisch außerhalb des Modells anhand von bild_ref.

SCHÄDEN-MARKER (Abschnitt 7.4):
- Jeder Schaden beginnt mit einem Marker der Form "[Nr] S=.., V=.., D=.."
  (z. B. "[19] S=0, V=0, D=2 BSP-ID 006-02-04"). Die Zahl in eckigen Klammern ist
  die Schadensnummer; die Werte S/V/D übernimm in die Felder s, v, d.
- Behandle JEDEN solchen Marker als GENAU EINEN Schaden — extrahiere alle.
- Eckige Klammern, die TEXT enthalten (z. B. "[Längsriss mit Aussinterung]"),
  gehören zur Beschreibung und sind KEIN neuer Schaden.
- Auch bei OCR-Verzerrungen (z. B. "(19)" statt "[19]") zählt jeder solche Marker.

BEWERTUNG (Abschnitt 7.5):
- Direkt nach 7.4 folgt die Bewertung mit der Zustandsnote und zu JEDEM Maximum
  S, V und D ein Erläuterungstext darunter (welche Schäden bzw. welche Befunde
  diesen Maximalwert begründen).
- Übernimm diesen Erläuterungstext WORTWÖRTLICH in max_s_begruendung,
  max_v_begruendung bzw. max_d_begruendung (mehrzeilige Absätze
  zusammenführen, keine eigene Interpretation).
- Wenn für eine Klasse keine Begründung im Dokument steht (oder 7.5 fehlt):
  das jeweilige Feld null lassen — NICHT erfinden.

QUELLSEITEN (source_pages):
- Trage für die wichtigsten Felder die Seitenzahl ein, auf der der Wert steht:
  bauwerksnummer, aktuelle Zustandsnote, baujahr_ueberbau, dtv_gesamt.
- Nutze die ===== PAGE n ===== Markierungen im Text.

KOORDINATEN (Abschnitt 5.1.1 "GIS-Koordinaten", falls vorhanden):
- Das Dokument kann ZWEI Koordinatenpaare enthalten: "Gauß-Krüger-Koordinaten" UND
  "UTM-Koordinaten". Verwende AUSSCHLIESSLICH die UTM-Koordinaten:
  utm_rechtswert + utm_hochwert aus dem UTM-Block und utm_bezugssystem aus der Zeile
  "Bezugssystem" (z. B. "ETRS_UTM_NW489"). Übernimm NIEMALS die Gauß-Krüger-Werte.
- Wenn KEIN GIS-/UTM-Koordinatenabschnitt vorhanden ist: alle drei Felder null lassen.
  Niemals raten oder aus anderen Zahlen (Stationen, Netzknoten, IBwNr) ableiten.

PRÜFUNGEN (Abschnitt 7.3 "Durchgeführte Prüfungen"):
- Die Tabelle hat die Spalten: Art | Datum | Zyklus | Zustand. Extrahiere pro Zeile
  art, datum, zyklus_monate und zustandsnote (der Wert der Spalte "Zustand").

EMPFEHLUNGEN (Abschnitt 7.6 "Empfehlungen"):
- Abschnitt 7.6 listet Maßnahmenempfehlungen. Jede beginnt mit dem Marker
  "Maßnahmenempfehlung {Nr}" (Nr in geschweiften Klammern).
- Extrahiere pro Empfehlung in das Array empfehlungen:
  · nr                    = die Zahl im Marker {Nr}
  · art_der_leistung      = Text der Zeile "Art der Leistung"
  · dringlichkeit         = Text der Zeile "Dringlichkeit" (falls vorhanden)
  · geschaetzte_kosten_eur= die Zahl vor "EURO" (bei "--" null lassen)
  · ausfuehrungsjahr      = Jahr aus "Dauer der Maßnahme / Ausführungsjahr" (falls vorhanden)
  · bemerkung             = Text der Zeile "Bemerkung"
  · zugeordnete_schaeden  = die Schadensnummern aus der Zeile "Zugeordnete Schäden:"
                            (z. B. "[54], [64], [65]" → [54, 64, 65]); sonst leere Liste
- Behandle JEDEN "Maßnahmenempfehlung {Nr}"-Marker als GENAU EINE Empfehlung.
- Wenn Abschnitt 7.6 leer ist ("Keine Angaben") oder fehlt: empfehlungen leer lassen.
- Verwechsle dies NICHT mit Abschnitt 8.3 (Bau- und Erhaltungsmaßnahmen) — 8.3 NICHT extrahieren.

ABSCHNITTE — extrahiere NUR:
- Abschnitt 2/5/9: Stammdaten (Identität, Lage, Konstruktion, Verkehr)
- Abschnitt 7.3: Prüfungshistorie (pruefungen) — mit Zustandsnote
- Abschnitt 7.4: Schäden (schaeden) — mit Fotozuordnung
- Abschnitt 7.6: Empfehlungen (empfehlungen) — mit zugeordneten Schäden
- Abschnitt 6 (Konstruktionsteile) und Abschnitt 8.3 NICHT extrahieren.
"""


def _mime(ext: str) -> str:
    return "image/jpeg" if ext.lower() in ("jpg", "jpeg") else f"image/{ext.lower()}"


def count_instruction(expected: int | None) -> str | None:
    """Per-document instruction pinning the exact number of damages to extract.

    `expected` is the deterministic section-7.4 count (pdf_text.count_schaeden).
    Returned only when it's a usable positive number; None otherwise (so a count
    of 0 or an unknown count never forces the model). Shared by both LLM paths.
    """
    if not expected:
        return None
    return (
        f"\n\nWICHTIG: Im Abschnitt 7.4 sind GENAU {expected} Schäden aufgeführt "
        f"(jeder mit einem Marker '[Nr] S=.., V=.., D=..'). Extrahiere ALLE "
        f"{expected} Schäden vollständig — lasse keinen aus und erfinde keinen."
    )


def check_count(bridge: BridgeExtraction, expected: int | None, model: str) -> None:
    """Warn (don't raise) when the LLM's damage count disagrees with the
    deterministic section-7.4 count. The bridge is still persisted; the
    discrepancy is logged so it surfaces for review."""
    if not expected:
        return
    got = len(bridge.schaeden)
    if got != expected:
        log.warning("Schaden count mismatch (%s): LLM extracted %d, section 7.4 has %d",
                    model, got, expected)


def missing_schaeden(bridge: BridgeExtraction, marker_numbers: list[int]) -> list[int]:
    """Marker numbers from section 7.4 that the LLM did NOT return (by schaden_nr)."""
    got = {s.schaden_nr for s in bridge.schaeden if s.schaden_nr is not None}
    return [n for n in dict.fromkeys(marker_numbers) if n not in got]


def retry_instruction(missing: list[int], expected: int) -> str:
    """Targeted feedback for a second pass: name the damages the model dropped so
    it adds exactly those, and re-state the total so it returns the full set."""
    nums = ", ".join(f"[{n}]" for n in missing)
    return (
        f"\n\nDeine vorige Antwort war UNVOLLSTÄNDIG. Im Abschnitt 7.4 stehen genau "
        f"{expected} Schäden, aber es fehlen die mit diesen Nummern: {nums}. "
        f"Gib erneut ALLE {expected} Schäden zurück (einschließlich der fehlenden), "
        f"jeweils mit korrektem schaden_nr. Erfinde KEINE Nummer, die nicht als "
        f"'[Nr] S=..' im Dokument vorkommt."
    )


def extract(text: str, *, expected_schaeden: int | None = None,
            feedback: str | None = None, temperature: float = 0.0) -> tuple[BridgeExtraction, dict]:
    """Run the text-only extraction call.

    Photos are NOT passed to the model: photo↔damage matching is resolved
    deterministically afterwards (see ingestion.photo_match) from each damage's
    `bild_ref` and the on-page caption. The model's only photo-related job is to
    copy the Bild: reference verbatim into bild_ref.

    Args:
        text: Full page-tagged document text from pdf_text.extract_text().

    Returns:
        (BridgeExtraction, usage_dict)  where usage_dict has input_tokens,
        output_tokens, model.

    Raises:
        ValueError: if the LLM response fails Pydantic validation or the
                    domain gate (missing bauwerksnummer, bad grade range, etc.)
    """
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    parts: list[types.Part] = [
        types.Part.from_text(text=_SYSTEM_PROMPT),
        types.Part.from_text(text=f"\n\nDOKUMENT:\n{text}"),
        types.Part.from_text(text="\n\nGib die Antwort als JSON gemäß dem Schema aus."),
    ]
    instr = count_instruction(expected_schaeden)
    if instr:
        parts.append(types.Part.from_text(text=instr))
    if feedback:
        parts.append(types.Part.from_text(text=feedback))

    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=BridgeExtraction,
            temperature=temperature,
        ),
    )

    bridge = BridgeExtraction.model_validate(json.loads(response.text))
    _domain_gate(bridge)
    check_count(bridge, expected_schaeden, config.GEMINI_MODEL)

    usage = {
        "input_tokens": response.usage_metadata.prompt_token_count,
        "output_tokens": response.usage_metadata.candidates_token_count,
        "model": config.GEMINI_MODEL,
    }
    return bridge, usage


_UMLAUTS = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
})


def _slug_foto_key(key: str) -> str:
    """Make a foto_key safe as a Storage object key. Supabase rejects non-ASCII
    keys (the model emits German terms like 'längsriss' → InvalidKey), so
    transliterate umlauts/ß, lowercase, and keep only [a-z0-9_]."""
    s = key.translate(_UMLAUTS).lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s).strip("_")
    return s[:40] or "foto"


def _domain_gate(bridge: BridgeExtraction) -> None:
    """Raise ValueError for any semantic violation not caught by Pydantic.

    Photo links are NOT checked here — they're set later and validated by
    construction in ingestion.photo_match (which only ever assigns an in-range
    foto_index and a unique foto_key)."""
    if not bridge.bauwerksnummer:
        raise ValueError("bauwerksnummer is missing")
    if not bridge.pruefungen:
        raise ValueError("no pruefungen extracted — document may be incomplete")

    for p in bridge.pruefungen:
        if p.zustandsnote is not None and not (1.0 <= p.zustandsnote <= 4.0):
            raise ValueError(f"grade out of range: {p.zustandsnote}")
