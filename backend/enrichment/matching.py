"""Phase 5c — contractor capability matching.

Computes the set of Leistungsbereiche (PQ-VOB codes) a bridge requires, driven by
its CONSTRUCTION TYPE (validated against the curated contractor↔bridge data):

  every bridge   → 311_11 (Betonerhaltung) + 311_12 (Abdichtung) + 613_01 (general)
  Spannbeton     → + 311_03 (Spannbetonarbeiten)
  Steel/composite→ + 311_06 + 311_07 + 311_10 (Stahlverbund/Stahlbau/Korrosionsschutz)

This set is stored on the bridge as `benoetigte_leistungsbereiche`; the FRONTEND
loads contractors whose `leistungsbereiche` overlap (&&) it and filters them by
haversine distance / Umkreis in-browser. Matching stays "dynamic" while the
domain logic is computed once, in the batch.

Codes are in the underscore form used by the contractors table (e.g. "311_03").
"""
import re

from backend.domain import mappings as M
from backend.extraction.schemas import BridgeExtraction

# "Stahl" / "Stahlträger" / "Stahlverbund" → steel, but NOT "Stahlbeton"
# (reinforced concrete, which is a concrete bridge, covered by the always-set).
_STAHL_RE = re.compile(r"\bstahl(?!beton)")
_SPANNBETON_RE = re.compile(r"\bspannbeton")


def required_leistungsbereiche(bridge: BridgeExtraction) -> list[str]:
    """Sorted, de-duplicated LB codes the bridge requires (construction-driven)."""
    codes: set[str] = set(M.LEISTUNGSBEREICH_ALWAYS)

    material = " ".join(filter(None, [
        bridge.hauptbaustoff, bridge.konstruktion, bridge.bauwerksart,
    ])).lower()

    if _SPANNBETON_RE.search(material):
        codes.update(M.LEISTUNGSBEREICH_SPANNBETON)
    if _STAHL_RE.search(material):
        codes.update(M.LEISTUNGSBEREICH_STAHL)

    return sorted(codes)
