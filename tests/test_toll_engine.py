"""Tests for the toll engine - portal detection and toll calculation."""

from datetime import datetime

from src.models import VehicleCategory
from src.toll_calculator import calculate_toll, _get_time_band
from src.toll_engine import find_portals_crossed, _haversine_m
from src.models import TimeBand


def test_haversine_known_distance():
    """Test haversine with a known distance in Santiago."""
    # Plaza Italia to Estación Central is ~4.5km
    d = _haversine_m(-33.4372, -70.6340, -33.4520, -70.6790)
    assert 3500 < d < 5500


def test_time_band_weekday_peak():
    dt = datetime(2026, 3, 4, 8, 0)  # Wednesday 8am
    assert _get_time_band(dt) == TimeBand.TBP


def test_time_band_weekday_offpeak():
    dt = datetime(2026, 3, 4, 14, 0)  # Wednesday 2pm
    assert _get_time_band(dt) == TimeBand.TBFP


def test_time_band_sunday():
    dt = datetime(2026, 3, 8, 8, 0)  # Sunday 8am
    assert _get_time_band(dt) == TimeBand.TBFP


def test_find_portals_on_autopista_central_route():
    """Simulate a route going north on Autopista Central (Eje Norte-Sur).

    Route: from Alameda area northward through central Santiago toward Quilicura.
    Should cross northbound portals PA10, PA31, PA13, PA16, PA17, PA18.
    """
    route_points = [
        (-33.475, -70.662),   # South of Alameda
        (-33.472, -70.662),   # Near PA10 (Carlos Valdovinos - Alameda)
        (-33.460, -70.661),
        (-33.448, -70.658),   # Near PA31 (Alameda - Río Mapocho)
        (-33.435, -70.660),
        (-33.425, -70.663),   # Near PA13 (Río Mapocho - 14 de la Fama)
        (-33.410, -70.667),
        (-33.395, -70.670),   # Near PA16 (14 de la Fama - A. Vespucio Norte)
        (-33.380, -70.674),
        (-33.368, -70.678),   # Near PA17 (A. Vespucio Norte - Ruta 5 Norte)
        (-33.355, -70.681),   # Near PA18 (Northern section)
    ]
    crossed = find_portals_crossed(route_points)
    assert len(crossed) > 0
    highway_names = {p["highway"] for p in crossed}
    assert "Autopista Central" in highway_names


def test_calculate_toll_basic():
    """Test toll calculation with mock portal data."""
    portals = [
        {
            "highway": "Autopista Central",
            "portal_id": "test_1",
            "portal_name": "Test Portal 1",
            "lat": -33.40,
            "lng": -70.66,
            "rates": {
                "cat_4": {"tbfp": 300, "tbp": 600, "ts": 900},
            },
        },
        {
            "highway": "Autopista Central",
            "portal_id": "test_2",
            "portal_name": "Test Portal 2",
            "lat": -33.45,
            "lng": -70.66,
            "rates": {
                "cat_4": {"tbfp": 250, "tbp": 500, "ts": 750},
            },
        },
    ]
    dt = datetime(2026, 3, 4, 14, 0)  # Off-peak
    result = calculate_toll(portals, dt, VehicleCategory.CAT_4)
    assert result.total_clp == 550
    assert len(result.portals_crossed) == 2


def test_calculate_toll_peak():
    portals = [
        {
            "highway": "Test",
            "portal_id": "t1",
            "portal_name": "T1",
            "lat": -33.40,
            "lng": -70.66,
            "rates": {"cat_4": {"tbfp": 300, "tbp": 600, "ts": 900}},
        },
    ]
    dt = datetime(2026, 3, 4, 8, 0)  # Peak
    result = calculate_toll(portals, dt, VehicleCategory.CAT_4)
    assert result.total_clp == 600
