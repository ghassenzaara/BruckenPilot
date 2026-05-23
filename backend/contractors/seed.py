"""Phase 2 — seed the contractors table from contractors_geocoded.json.

Run from the project root:
    python -m backend.contractors.seed

Idempotent: upserts on pq_nummer. Rows without a pq_nummer or without
coordinates are skipped (a contractor with no location can't be distance-filtered)
and reported at the end.
"""
import json

from backend import config
from backend.db.client import get_client

CHUNK = 100


def parse_leistungsbereiche(raw):
    """'311_01,613_01' -> ['311_01', '613_01']. Stored verbatim (underscore form)."""
    if not raw:
        return []
    return [code.strip() for code in str(raw).split(",") if code.strip()]


def build_row(record):
    return {
        "pq_nummer": record.get("pq_nummer"),
        "firmenname": record.get("firmenname"),
        "strasse": record.get("strasse"),
        "plz": record.get("plz"),
        "ort": record.get("ort"),
        "land": record.get("land"),
        "telefon": record.get("telefon"),
        "email": record.get("email"),
        "lat": record.get("lat"),
        "lon": record.get("lon"),
        "leistungsbereiche": parse_leistungsbereiche(record.get("leistungsbereiche")),
        "spezialisierungen": record.get("spezialisierungen"),
    }


def main():
    path = config.CONTRACTORS_GEOCODED_JSON
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run geocoding.py first to produce it."
        )

    with open(path, encoding="utf-8") as f:
        records = json.load(f)

    rows, skipped_no_pq, skipped_no_coords = [], 0, 0
    for rec in records:
        if not rec.get("pq_nummer"):
            skipped_no_pq += 1
            continue
        if rec.get("lat") is None or rec.get("lon") is None:
            skipped_no_coords += 1
            continue
        rows.append(build_row(rec))

    client = get_client()
    for i in range(0, len(rows), CHUNK):
        batch = rows[i:i + CHUNK]
        client.table("contractors").upsert(batch, on_conflict="pq_nummer").execute()
        print(f"  upserted {min(i + CHUNK, len(rows))}/{len(rows)}")

    print(f"\nDone. {len(rows)} contractors seeded.")
    if skipped_no_coords:
        print(f"  skipped {skipped_no_coords} without coordinates")
    if skipped_no_pq:
        print(f"  skipped {skipped_no_pq} without pq_nummer")


if __name__ == "__main__":
    main()
