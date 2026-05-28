"""Phase 5a — UTM (ETRS89) → WGS84 conversion.

Robust to the two real-world hazards seen in the sample PDFs:
  1. Rechtswert/Hochwert can be swapped by text extraction → disambiguate by
     magnitude (German northing is always >1M, easting always <1M).
  2. The document carries both Gauß-Krüger and UTM coords → the LLM is asked for
     UTM; this module assumes ETRS89/UTM input and validates the result lands
     inside Germany, returning None (no map pin) rather than a wrong location.
"""
from functools import lru_cache

from pyproj import Transformer

from backend.domain.bounds import in_germany

# AdV convention: zone 33N for the eastern Bundesländer, 32N for the rest.
_ZONE33_STATES = {"BB", "BE", "MV", "SN", "ST"}
_EPSG_32N = "EPSG:25832"
_EPSG_33N = "EPSG:25833"


def _epsg_for(bezugssystem: str | None) -> str:
    """Pick the UTM zone EPSG from a bezugssystem string like 'ETRS_UTM_BY489'."""
    if bezugssystem:
        s = bezugssystem.upper()
        if "33" in s or "UTM33" in s:
            return _EPSG_33N
        for code in _ZONE33_STATES:
            if f"_{code}" in s or f" {code}" in s:
                return _EPSG_33N
    return _EPSG_32N   # default: covers NW, BY and most of Germany


@lru_cache(maxsize=4)
def _transformer(epsg: str) -> Transformer:
    return Transformer.from_crs(epsg, "EPSG:4326", always_xy=True)


def to_wgs84(
    rechtswert: float | None,
    hochwert: float | None,
    bezugssystem: str | None = None,
) -> tuple[float, float] | None:
    """Return (lat, lon) in WGS84, or None if inputs are missing/out of bounds."""
    if rechtswert is None or hochwert is None:
        return None
    try:
        a, b = float(rechtswert), float(hochwert)
    except (TypeError, ValueError):
        return None

    # Disambiguate easting vs northing by magnitude (handles swapped labels):
    # in Germany the northing (~5–6M) is always the larger of the two.
    easting, northing = min(a, b), max(a, b)

    lon, lat = _transformer(_epsg_for(bezugssystem)).transform(easting, northing)
    if not in_germany(lat, lon):
        return None
    return (round(lat, 6), round(lon, 6))
