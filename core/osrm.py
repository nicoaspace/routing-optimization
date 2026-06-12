"""
OSRM client — distance matrix via Table API and route geometry via Route API.
Uses the public demo server (router.project-osrm.org).
Override OSRM_BASE env var to point at a self-hosted instance.
"""

import math
import os
import time
from typing import Optional

import requests

OSRM_BASE = os.getenv("OSRM_BASE", "http://router.project-osrm.org")
_TIMEOUT = 30
_RETRIES = 3


def _coords_to_str(coords: list[tuple[float, float]]) -> str:
    """Convert [(lat, lon), ...] to OSRM 'lon,lat;lon,lat;...' string."""
    return ";".join(f"{lon},{lat}" for lat, lon in coords)


def get_distance_matrix(
    coords: list[tuple[float, float]],
) -> list[list[float]]:
    """
    Return an N×N driving-distance matrix (metres) via the OSRM Table API.
    A single HTTP request replaces the O(N²) loop in the original code.
    """
    coord_str = _coords_to_str(coords)
    url = f"{OSRM_BASE}/table/v1/driving/{coord_str}?annotations=distance"

    last_exc: Optional[Exception] = None
    for attempt in range(_RETRIES):
        try:
            resp = requests.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == "Ok":
                matrix = data["distances"]
                # Replace None values (unreachable pairs) with a large penalty
                big = 10_000_000
                return [
                    [d if d is not None else big for d in row]
                    for row in matrix
                ]
            raise RuntimeError(f"OSRM returned code: {data.get('code')}")
        except Exception as exc:
            last_exc = exc
            if attempt < _RETRIES - 1:
                time.sleep(2**attempt)

    raise RuntimeError(f"OSRM Table API failed after {_RETRIES} attempts: {last_exc}")


def get_route_geometry(
    waypoints: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """
    Return a list of (lat, lon) points representing the real road path for a
    sequence of waypoints.  Falls back to straight-line segments on failure.
    """
    if len(waypoints) < 2:
        return waypoints

    coord_str = _coords_to_str(waypoints)
    url = (
        f"{OSRM_BASE}/route/v1/driving/{coord_str}"
        "?overview=full&geometries=geojson"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == "Ok":
            # GeoJSON coords are [lon, lat]; flip for folium
            geo = data["routes"][0]["geometry"]["coordinates"]
            return [(lat, lon) for lon, lat in geo]
    except Exception:
        pass

    return waypoints  # straight-line fallback


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (used only as a fallback)."""
    R = 6_371_000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
