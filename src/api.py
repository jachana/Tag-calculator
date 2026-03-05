"""FastAPI route definitions."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from src.models import (
    CompareRoutesResponse,
    FuelEstimate,
    RouteComparison,
    RouteInfo,
    TollEstimateRequest,
    TollEstimateResponse,
)
from src.route_service import geocode, get_route, get_routes
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

    return TollEstimateResponse(
        route=RouteInfo(
            distance_km=round(distance_km, 1),
            duration_min=round(duration_min, 1),
            polyline=encoded_polyline,
        ),
        toll_estimate=toll_estimate,
        fuel_estimate=_build_fuel_estimate(distance_km),
    )


def _build_fuel_estimate(distance_km: float) -> FuelEstimate:
    liters = distance_km * RAV4_L_PER_100KM / 100
    return FuelEstimate(
        liters=round(liters, 2),
        cost_clp=round(liters * GAS_PRICE_CLP_PER_LITER),
        consumption_lper100km=RAV4_L_PER_100KM,
        price_per_liter_clp=GAS_PRICE_CLP_PER_LITER,
        vehicle_name="Toyota RAV4 2.0L",
    )


@router.post("/compare-routes", response_model=CompareRoutesResponse)
async def compare_routes(req: TollEstimateRequest):
    """Return multiple alternative routes with toll + fuel comparison."""
    try:
        origin = await geocode(req.origin)
        destination = await geocode(req.destination)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        alt_routes = await get_routes(origin, destination)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    departure = req.departure_time or datetime.now()
    comparisons: list[RouteComparison] = []

    for encoded_polyline, distance_km, duration_min, points in alt_routes:
        portals_crossed = find_portals_crossed(points)
        toll_estimate = calculate_toll(portals_crossed, departure, req.vehicle_category)
        fuel = _build_fuel_estimate(distance_km)

        comparisons.append(RouteComparison(
            route=RouteInfo(
                distance_km=round(distance_km, 1),
                duration_min=round(duration_min, 1),
                polyline=encoded_polyline,
            ),
            toll_estimate=toll_estimate,
            fuel_estimate=fuel,
            trip_total_clp=toll_estimate.total_clp + fuel.cost_clp,
        ))

    # Sort by total trip cost (cheapest first)
    comparisons.sort(key=lambda c: c.trip_total_clp)

    return CompareRoutesResponse(routes=comparisons)


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
