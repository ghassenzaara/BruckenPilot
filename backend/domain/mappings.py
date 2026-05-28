"""Tunable domain tables for scoring and contractor matching.

Everything here is a *default* meant to be reviewed by a domain expert. The
pipeline logic reads these tables; changing a weight here re-tunes the system
without touching code.
"""
import re

# ── Scoring: road-class criticality weight ──────────────────────────────────
# Higher class road → failure affects more / higher-value traffic.
ROADCLASS_WEIGHT = {
    "A": 1.00,   # Autobahn
    "B": 0.80,   # Bundesstraße
    "St": 0.60,  # Staatsstraße
    "L": 0.40,   # Landesstraße
    "K": 0.25,   # Kreisstraße
    "sonstige": 0.10,
}
ROADCLASS_DEFAULT = 0.10


def normalize_strassenklasse(value: str | None) -> str | None:
    """LLM returns full names ('Bundesautobahn', 'Staatsstraße') → canonical code."""
    if not value:
        return None
    v = value.strip()
    if v in ROADCLASS_WEIGHT:
        return v
    lv = v.lower()
    if "autobahn" in lv:
        return "A"
    if "bundesstra" in lv:
        return "B"
    if "staatsstra" in lv:
        return "St"
    if "landesstra" in lv:
        return "L"
    if "kreisstra" in lv:
        return "K"
    return "sonstige"


# Canonical class code keyed by the letter prefix of a Strasse designation.
_STRASSE_PREFIX = {"a": "A", "b": "B", "st": "St", "l": "L", "k": "K"}


def strassenklasse_from_strasse(strasse: str | None) -> str | None:
    """Derive the road class from the Strasse designation deterministically.

    German road numbers always carry the class as a letter prefix:
    'L 2086' → 'L', 'St 2086' → 'St', 'B 304' → 'B', 'A 8' → 'A', 'K 12' → 'K'.
    Returns the canonical code, or None if the leading token isn't a known class
    (callers then fall back to the LLM's strassenklasse)."""
    if not strasse:
        return None
    m = re.match(r"\s*([A-Za-z]{1,2})\s*\d", strasse)   # letters right before the number
    return _STRASSE_PREFIX.get(m.group(1).lower()) if m else None


def normalize_umfahrt(value: str | None) -> str | None:
    """LLM returns phrases ('Leicht möglich (bis 5 km Umweg)') → canonical code."""
    if not value:
        return None
    v = value.strip().lower()
    if v in ("leicht", "mittel", "schwer", "nicht_moeglich"):
        return v
    if "nicht" in v or "unmög" in v or "keine" in v:
        return "nicht_moeglich"
    if "schwer" in v:
        return "schwer"
    if "mittel" in v:
        return "mittel"
    if "leicht" in v or "gut" in v:
        return "leicht"
    return None

# ── Scoring: detour difficulty for heavy vehicles ───────────────────────────
# Harder/impossible detour → bridge failure is more disruptive → more critical.
UMFAHRT_WEIGHT = {
    "nicht_moeglich": 1.00,
    "schwer": 0.75,
    "mittel": 0.40,
    "leicht": 0.10,
}
UMFAHRT_DEFAULT = 0.40

# ── Scoring: traffic normalization ──────────────────────────────────────────
# log-scaled DTV; this value maps to criticality 1.0 (very heavy traffic).
DTV_REFERENCE = 150_000

# ── Scoring: cost factor ────────────────────────────────────────────────────
# Rough intervention cost = brueckenflaeche_m2 * EUR/m2 (massnahme-type rate).
# Used only for the *relative* cost_factor; not a real cost estimate.
COST_RATE_EUR_PER_M2 = {
    "instandsetzung": 1_500,
    "verstaerkung": 2_500,
    "erneuerung": 4_000,
    "default": 2_000,
}
# Budget scale for inverting cost into a 0–1 factor (cheaper job → higher factor).
COST_REFERENCE_BUDGET = 500_000

# ── Contractor capability matching (PQ-VOB Leistungsbereiche, underscore form) ──
# Validated code meanings (provided by the project owner):
#   613_01  Komplettleistungen Brückenbau          — general; every bridge
#   311_11  Betonerhaltungsarbeiten                 — concrete preservation; every bridge
#   311_12  Abdichtungsarbeiten Ingenieurbau        — sealing/waterproofing; every bridge
#   311_03  Spannbetonarbeiten                      — prestressed concrete only
#   311_06  Stahlverbundarbeiten                    — steel-composite only
#   311_07  Stahlbauarbeiten                        — steel construction only
#   311_10  Korrosionsschutzarbeiten Ingenieurbau   — corrosion protection (steel) only
#
# The required set is driven by the bridge's CONSTRUCTION TYPE, not by individual
# damage keywords (confirmed against the curated contractor↔bridge data). The
# frontend filters contractors whose leistungsbereiche overlap (&&) this set.

# Every road bridge: general bridge services + concrete preservation + sealing.
LEISTUNGSBEREICH_ALWAYS = ["311_11", "311_12", "613_01"]

# Prestressed-concrete construction (Spannbeton).
LEISTUNGSBEREICH_SPANNBETON = ["311_03"]

# Steel / steel-composite construction: composite + steel + corrosion protection.
LEISTUNGSBEREICH_STAHL = ["311_06", "311_07", "311_10"]
