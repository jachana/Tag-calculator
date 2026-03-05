"""Toll engine: detects which portals a route crosses using geofencing."""

from __future__ import annotations

import json
import math
from pathlib import Path

from src.config import PORTAL_DETECTION_RADIUS_M, TOLL_DATA_DIR


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance in meters between two points using Haversine formula."""
    R = 6_371_000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Bearing in degrees from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lng2 - lng1)
    x = math.sin(dlam) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _load_all_highways() -> list[dict]:
    """Load all highway JSON files from toll_data/."""
    highways = []
    for path in sorted(TOLL_DATA_DIR.glob("*.json")):
        if path.name == "schedules.json":
            continue
        with open(path) as f:
            highways.append(json.load(f))
    return highways


def _interpolate_segment(
    lat1: float, lng1: float, lat2: float, lng2: float, max_gap_m: float = 100
) -> list[tuple[float, float]]:
    """Interpolate extra points along a segment so no gap exceeds max_gap_m.

    Returns a list of (lat, lng) including the start but NOT the end point
    (to avoid duplicates when chaining segments).
    """
    dist = _haversine_m(lat1, lng1, lat2, lng2)
    if dist <= max_gap_m:
        return [(lat1, lng1)]

    n_steps = max(2, int(math.ceil(dist / max_gap_m)))
    points = []
    for s in range(n_steps):
        frac = s / n_steps
        lat = lat1 + frac * (lat2 - lat1)
        lng = lng1 + frac * (lng2 - lng1)
        points.append((lat, lng))
    return points


def _densify_route(
    route_points: list[tuple[float, float]], max_gap_m: float = 100
) -> list[tuple[float, float]]:
    """Add interpolated points so no consecutive pair is more than max_gap_m apart."""
    if len(route_points) < 2:
        return list(route_points)

    dense: list[tuple[float, float]] = []
    for i in range(len(route_points) - 1):
        lat1, lng1 = route_points[i]
        lat2, lng2 = route_points[i + 1]
        dense.extend(_interpolate_segment(lat1, lng1, lat2, lng2, max_gap_m))
    dense.append(route_points[-1])
    return dense


def find_portals_crossed(
    route_points: list[tuple[float, float]],
    radius_m: float = PORTAL_DETECTION_RADIUS_M,
) -> list[dict]:
    """Walk the route polyline and detect portal crossings.

    Returns a list of dicts:
      {highway, portal_id, portal_name, lat, lng, rates}
    in the order they are crossed.
    """
    highways = _load_all_highways()

    # Build flat list of all portals with their highway context
    all_portals = []
    for hw in highways:
        for portal in hw.get("portals", []):
            # Skip comment-only entries (e.g. {"_comment": "..."})
            if "id" not in portal:
                continue
            all_portals.append({
                "highway": hw["display_name"],
                "highway_id": hw["highway"],
                "portal_id": portal["id"],
                "portal_name": portal["name"],
                "lat": portal["lat"],
                "lng": portal["lng"],
                "rates": portal["rates"],
            })

    # Densify the route so we don't skip portals between sparse OSRM points
    dense_points = _densify_route(route_points, max_gap_m=80)

    crossed = []
    crossed_ids = set()  # avoid double-counting same portal

    for i in range(len(dense_points) - 1):
        lat1, lng1 = dense_points[i]
        lat2, lng2 = dense_points[i + 1]

        for portal in all_portals:
            if portal["portal_id"] in crossed_ids:
                continue

            # Check distance from both segment endpoints to portal
            d1 = _haversine_m(lat1, lng1, portal["lat"], portal["lng"])
            d2 = _haversine_m(lat2, lng2, portal["lat"], portal["lng"])

            if min(d1, d2) <= radius_m:
                crossed_ids.add(portal["portal_id"])
                crossed.append({
                    "highway": portal["highway"],
                    "portal_id": portal["portal_id"],
                    "portal_name": portal["portal_name"],
                    "lat": portal["lat"],
                    "lng": portal["lng"],
                    "rates": portal["rates"],
                })

    return crossed
