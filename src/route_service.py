"""Route service using free OSRM and Nominatim APIs."""

from __future__ import annotations

import httpx
import polyline as polyline_codec

from src.config import NOMINATIM_BASE_URL, NOMINATIM_USER_AGENT, OSRM_BASE_URL
from src.models import LatLng


async def geocode(address: str) -> LatLng:
    """Convert address string to lat/lng using Nominatim.

    Also accepts 'lat,lng' format directly.
    """
    # Check if already coordinates
    if "," in address:
        parts = address.split(",")
        try:
            lat, lng = float(parts[0].strip()), float(parts[1].strip())
            return LatLng(lat=lat, lng=lng)
        except (ValueError, IndexError):
            pass

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{NOMINATIM_BASE_URL}/search",
            params={
                "q": address,
                "format": "json",
                "limit": 1,
                "countrycodes": "cl",
                "viewbox": "-70.85,-33.6,-70.45,-33.3",  # Santiago bounding box
                "bounded": 1,
            },
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            raise ValueError(f"Could not geocode address: {address}")
        return LatLng(lat=float(results[0]["lat"]), lng=float(results[0]["lon"]))


async def get_route(
    origin: LatLng, destination: LatLng
) -> tuple[str, float, float, list[tuple[float, float]]]:
    """Get route from OSRM.

    Returns (encoded_polyline, distance_km, duration_min, decoded_points).
    """
    coords = f"{origin.lng},{origin.lat};{destination.lng},{destination.lat}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{OSRM_BASE_URL}/route/v1/driving/{coords}",
            params={
                "overview": "full",
                "geometries": "polyline",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError("OSRM could not find a route")

    route = data["routes"][0]
    encoded = route["geometry"]
    distance_km = route["distance"] / 1000.0
    duration_min = route["duration"] / 60.0

    # Decode polyline to list of (lat, lng) tuples
    points = polyline_codec.decode(encoded)  # returns [(lat, lng), ...]

    return encoded, distance_km, duration_min, points
