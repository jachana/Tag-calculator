from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class VehicleCategory(str, Enum):
    CAT_1 = "cat_1"  # Motorcycles, scooters
    CAT_4 = "cat_4"  # Autos, pickups (base)
    CAT_2 = "cat_2"  # Buses, trucks 2-axle
    CAT_3 = "cat_3"  # Buses, trucks with trailer


class TimeBand(str, Enum):
    TBFP = "tbfp"  # Fuera de punta (off-peak)
    TBP = "tbp"    # Punta (peak)
    TS = "ts"       # Saturación (saturation)


class LatLng(BaseModel):
    lat: float
    lng: float


class TollEstimateRequest(BaseModel):
    origin: str  # Address or "lat,lng"
    destination: str
    departure_time: datetime | None = None
    vehicle_category: VehicleCategory = VehicleCategory.CAT_4


class PortalCrossing(BaseModel):
    highway: str
    portal_id: str
    portal_name: str
    time_band: TimeBand
    fee_clp: int
    lat: float
    lng: float


class RouteInfo(BaseModel):
    distance_km: float
    duration_min: float
    polyline: str


class FuelEstimate(BaseModel):
    liters: float
    cost_clp: int
    consumption_lper100km: float
    price_per_liter_clp: int
    vehicle_name: str


class TollEstimateResponse(BaseModel):
    route: RouteInfo
    toll_estimate: TollEstimate
    fuel_estimate: FuelEstimate


class TollEstimate(BaseModel):
    total_clp: int
    currency: str = "CLP"
    portals_crossed: list[PortalCrossing]
