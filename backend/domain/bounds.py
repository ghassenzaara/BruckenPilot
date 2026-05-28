"""Coordinate bounds and rating ranges — the sanity gates for extracted data."""

# Generous WGS84 bounding box for Germany. Used to reject mis-projected or
# swapped coordinates (a bridge that lands in the ocean = bad input, drop it).
GERMANY_LAT = (47.0, 55.1)
GERMANY_LON = (5.5, 15.5)

# A UTM northing in Germany is always ~5.2M–6.1M; an easting always <1M.
# This lets us recover from text-extraction swaps of Rechtswert/Hochwert.
UTM_NORTHING_MIN = 1_000_000

# DIN 1076 grades (Zustandsnote) and S/V/D component ratings.
GRADE_MIN, GRADE_MAX = 1.0, 4.0
SVD_MIN, SVD_MAX = 0, 4


def in_germany(lat: float, lon: float) -> bool:
    return (GERMANY_LAT[0] <= lat <= GERMANY_LAT[1]
            and GERMANY_LON[0] <= lon <= GERMANY_LON[1])
