"""Toll engine: detects which portals a route crosses using entry/exit detection.

Instead of simple proximity to portal coordinates, this module:
1. Detects which portals the route passes near (tight radius, OSRM-snapped)
2. Groups detections by highway + axis
3. For each group with 2+ sequential detections, fills in ALL portals between
   the first and last detected — capturing the "entry/exit" concept
4. Filters by travel direction for highways with directional gantries
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from src.config import TOLL_DATA_DIR


# ---------------------------------------------------------------------------
# Geo utilities
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_all_highways() -> list[dict]:
    """Load all highway JSON files from toll_data/."""
    highways = []
    for path in sorted(TOLL_DATA_DIR.glob("*.json")):
        if path.name == "schedules.json":
            continue
        with open(path) as f:
            highways.append(json.load(f))
    return highways


# ---------------------------------------------------------------------------
# Route densification
# ---------------------------------------------------------------------------

def _densify_route(
    route_points: list[tuple[float, float]], max_gap_m: float = 30
) -> list[tuple[float, float]]:
    """Add interpolated points so no consecutive pair is more than max_gap_m apart."""
    if len(route_points) < 2:
        return list(route_points)

    dense: list[tuple[float, float]] = []
    for i in range(len(route_points) - 1):
        lat1, lng1 = route_points[i]
        lat2, lng2 = route_points[i + 1]
        dist = _haversine_m(lat1, lng1, lat2, lng2)
        if dist <= max_gap_m:
            dense.append((lat1, lng1))
        else:
            n_steps = max(2, int(math.ceil(dist / max_gap_m)))
            for s in range(n_steps):
                frac = s / n_steps
                dense.append((lat1 + frac * (lat2 - lat1), lng1 + frac * (lng2 - lng1)))
    dense.append(route_points[-1])
    return dense


# ---------------------------------------------------------------------------
# Portal sorting along highway axis
# ---------------------------------------------------------------------------

def _sort_portals_along_axis(portals: list[dict]) -> list[dict]:
    """Sort portals by geographic position along their axis.

    Uses latitude for primarily N-S highways, longitude for E-W highways.
    Returns a new sorted list (does not mutate input).
    """
    if len(portals) < 2:
        return list(portals)

    lats = [p["lat"] for p in portals]
    lngs = [p["lng"] for p in portals]
    lat_range = max(lats) - min(lats)
    lng_range = max(lngs) - min(lngs)

    if lat_range >= lng_range:
        # Primarily N-S: sort south to north (ascending latitude)
        return sorted(portals, key=lambda p: p["lat"])
    else:
        # Primarily E-W: sort west to east (ascending longitude)
        return sorted(portals, key=lambda p: p["lng"])


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def find_portals_crossed(
    route_points: list[tuple[float, float]],
    detection_radius_m: float = 80,
    min_portals_for_fill: int = 2,
) -> list[dict]:
    """Detect portal crossings using entry/exit logic.

    Algorithm:
    1. Densify the route (30 m gaps) so we don't miss portals between sparse
       OSRM polyline vertices.
    2. For every portal on every highway, check if *any* densified route point
       falls within ``detection_radius_m``.  Record the route-point index of
       the first hit (gives travel order).
    3. Group detected portals by (highway, axis).
    4. If a group has ≥ ``min_portals_for_fill`` detections, treat the first
       and last detected portal as "entry" and "exit".  Include *all* portals
       on that axis whose sorted position falls between entry and exit.
       - For highways **without** ``bidirectional_gantries``, only keep portals
         whose ``direction_bearing`` is roughly aligned (±90°) with the
         route's travel direction on the highway.
    5. If a group has fewer detections (e.g. 1), include the portal as-is.

    Returns a list of dicts with keys:
        highway, highway_id, portal_id, portal_name, lat, lng, rates
    """
    highways = _load_all_highways()
    dense_points = _densify_route(route_points, max_gap_m=30)

    # ------------------------------------------------------------------
    # Step 1: detect portal proximity matches
    # ------------------------------------------------------------------
    detections: list[dict] = []  # {hw, portal, route_idx}

    for hw in highways:
        for portal in hw.get("portals", []):
            if "id" not in portal:
                continue
            for idx, (lat, lng) in enumerate(dense_points):
                if _haversine_m(lat, lng, portal["lat"], portal["lng"]) <= detection_radius_m:
                    detections.append({
                        "hw": hw,
                        "portal": portal,
                        "route_idx": idx,
                    })
                    break  # one hit per portal is enough

    # ------------------------------------------------------------------
    # Step 2: group by (highway, axis)
    # ------------------------------------------------------------------
    groups: dict[tuple[str, str], list[dict]] = {}
    for det in detections:
        axis = det["portal"].get("axis", "default")
        key = (det["hw"]["highway"], axis)
        groups.setdefault(key, []).append(det)

    # ------------------------------------------------------------------
    # Step 3: for each group, apply entry/exit fill-in logic
    # ------------------------------------------------------------------
    crossed: list[dict] = []
    crossed_ids: set[str] = set()

    for (_hw_id, axis_name), group_dets in groups.items():
        hw = group_dets[0]["hw"]
        bidirectional = hw.get("bidirectional_gantries", False)

        # Sort detections by the order they appear along the route
        group_dets.sort(key=lambda d: d["route_idx"])

        detected_portals = [d["portal"] for d in group_dets]

        if len(detected_portals) >= min_portals_for_fill:
            # ---- Build sorted axis portal list ----
            all_axis_portals = _sort_portals_along_axis([
                p for p in hw.get("portals", [])
                if "id" in p and p.get("axis", "default") == axis_name
            ])
            order_map = {p["id"]: i for i, p in enumerate(all_axis_portals)}

            detected_orders = [order_map[p["id"]] for p in detected_portals]
            min_order = min(detected_orders)
            max_order = max(detected_orders)

            # ---- Compute route bearing on highway for direction filter ----
            first_det = group_dets[0]
            last_det = group_dets[-1]
            if first_det["route_idx"] != last_det["route_idx"]:
                route_bearing = _bearing(
                    dense_points[first_det["route_idx"]][0],
                    dense_points[first_det["route_idx"]][1],
                    dense_points[last_det["route_idx"]][0],
                    dense_points[last_det["route_idx"]][1],
                )
            else:
                route_bearing = None

            # ---- Fill in all portals between entry and exit ----
            for i, portal in enumerate(all_axis_portals):
                if not (min_order <= i <= max_order):
                    continue
                if portal["id"] in crossed_ids:
                    continue

                # Direction filter for highways with separate N/S gantries
                if not bidirectional and route_bearing is not None:
                    pb = portal.get("direction_bearing")
                    if pb is not None:
                        diff = abs(route_bearing - pb)
                        if diff > 180:
                            diff = 360 - diff
                        if diff > 90:
                            continue

                crossed_ids.add(portal["id"])
                crossed.append({
                    "highway": hw["display_name"],
                    "highway_id": hw["highway"],
                    "portal_id": portal["id"],
                    "portal_name": portal["name"],
                    "lat": portal["lat"],
                    "lng": portal["lng"],
                    "rates": portal["rates"],
                })
        else:
            # Single portal detection: include directly
            for det in group_dets:
                portal = det["portal"]
                if portal["id"] not in crossed_ids:
                    crossed_ids.add(portal["id"])
                    crossed.append({
                        "highway": hw["display_name"],
                        "highway_id": hw["highway"],
                        "portal_id": portal["id"],
                        "portal_name": portal["name"],
                        "lat": portal["lat"],
                        "lng": portal["lng"],
                        "rates": portal["rates"],
                    })

    return crossed
