"""FastAPI route definitions."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from src.models import (
    RouteInfo,
    TollEstimateRequest,
    TollEstimateResponse,
)
from src.route_service import geocode, get_route
from src.toll_calculator import calculate_toll
from src.toll_engine import find_portals_crossed

router = APIRouter(prefix="/api")


@router.post("/estimate-toll", response_model=TollEstimateResponse)
async def estimate_toll(req: TollEstimateRequest):
    """Estimate TAG toll fees for a route through Santiago."""
    try:
        origin = await geocode(req.origin)
        destination = await geocode(req.destination)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        encoded_polyline, distance_km, duration_min, points = await get_route(
            origin, destination
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    departure = req.departure_time or datetime.now()

    portals_crossed = find_portals_crossed(points)
    toll_estimate = calculate_toll(portals_crossed, departure, req.vehicle_category)

    return TollEstimateResponse(
        route=RouteInfo(
            distance_km=round(distance_km, 1),
            duration_min=round(duration_min, 1),
            polyline=encoded_polyline,
        ),
        toll_estimate=toll_estimate,
    )


@router.get("/highways")
async def list_highways():
    """Return all loaded highway data for the frontend map."""
    import json
    from src.config import TOLL_DATA_DIR

    highways = []
    for path in sorted(TOLL_DATA_DIR.glob("*.json")):
        if path.name == "schedules.json":
            continue
        with open(path) as f:
            highways.append(json.load(f))
    return highways
