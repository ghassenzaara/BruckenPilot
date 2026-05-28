"""Phase 5b — address → WGS84 fallback when a document has no UTM coordinates.

Some Bauwerksbücher (e.g. older NRW Landesbetrieb prints) carry no
"5.1.1 GIS-Koordinaten" block at all, so coords.to_wgs84() returns None and the
bridge would have no map pin. As a fallback we geocode the bridge's address via
Nominatim (OpenStreetMap). The result is approximate (street/town level), so the
pipeline records coord_source='geocoded' and the frontend can style it as such.

Network failures degrade gracefully to None (no pin) — they never crash the run.
"""
import time

import requests

from backend import config

_HEADERS = {"User-Agent": config.NOMINATIM_USER_AGENT}


def geocode(query: str, *, max_retries: int = 3) -> tuple[float, float] | None:
    """One Nominatim lookup, restricted to Germany. Returns (lat, lon), or None
    on a genuine no-result or after exhausting retries (transient errors)."""
    for attempt in range(max_retries):
        try:
            r = requests.get(
                config.NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 1, "countrycodes": "de"},
                headers=_HEADERS,
                timeout=10,
            )
            if r.status_code == 429 or r.status_code >= 500:  # rate limit / server hiccup
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
            return None  # valid response, address simply not found
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
            continue
    return None  # exhausted retries → no pin (never abort the pipeline)


def _clean(value) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s.lower() in ("", "nan", "none") else s


def _is_road_label(strasse: str) -> bool:
    """True for pure Autobahn/Bundesstraße labels like 'A 57' / 'B 9' — these
    geocode to a useless road midpoint, so they're skipped as a precise query."""
    s = strasse.upper().replace(" ", "")
    return bool(s) and s[0] in ("A", "B") and s[1:2].isdigit()


def geocode_bridge(bridge) -> tuple[float, float] | None:
    """Best-effort (lat, lon) for a bridge from its address fields, or None.

    Tries most specific first (bridge name / cross street + town), then falls
    back to the town centre — accurate enough for a map pin and proximity, which
    is why an approximate geocode is an acceptable fallback to missing coords.
    Respects Nominatim's 1 req/sec courtesy limit.
    """
    name = _clean(getattr(bridge, "name", None))
    ort = _clean(getattr(bridge, "ort", None))
    strasse = _clean(getattr(bridge, "strasse", None))
    land = _clean(getattr(bridge, "bundesland", None))

    attempts: list[str] = []
    if name and ort:
        attempts.append(f"{name}, {ort}, Deutschland")
    if strasse and ort and not _is_road_label(strasse):
        attempts.append(f"{strasse}, {ort}, Deutschland")
    if ort:
        attempts.append(f"{ort}, {land}, Deutschland" if land else f"{ort}, Deutschland")

    for q in attempts:
        coords = geocode(q)
        time.sleep(1)  # Nominatim: max 1 request/second
        if coords:
            return coords
    return None
