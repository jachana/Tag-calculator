"""FastAPI route definitions."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from src.models import (
    FuelEstimate,
    RouteInfo,
    TollEstimateRequest,
    TollEstimateResponse,
)
from src.route_service import geocode, get_route
from src.toll_calculator import calculate_toll
from src.toll_engine import find_portals_crossed

# Toyota RAV4 2.0L — blended city/highway for Santiago
RAV4_L_PER_100KM = 8.0
# Chilean 93-octane gasoline price (CLP/liter, approximate 2026)
GAS_PRICE_CLP_PER_LITER = 1250

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

    liters = distance_km * RAV4_L_PER_100KM / 100
    fuel_cost = round(liters * GAS_PRICE_CLP_PER_LITER)

    return TollEstimateResponse(
        route=RouteInfo(
            distance_km=round(distance_km, 1),
            duration_min=round(duration_min, 1),
            polyline=encoded_polyline,
        ),
        toll_estimate=toll_estimate,
        fuel_estimate=FuelEstimate(
            liters=round(liters, 2),
            cost_clp=fuel_cost,
            consumption_lper100km=RAV4_L_PER_100KM,
            price_per_liter_clp=GAS_PRICE_CLP_PER_LITER,
            vehicle_name="Toyota RAV4 2.0L",
        ),
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
            hw = json.load(f)
        # Filter out _comment entries from portals list
        hw["portals"] = [p for p in hw.get("portals", []) if "id" in p]
        highways.append(hw)
    return highways
