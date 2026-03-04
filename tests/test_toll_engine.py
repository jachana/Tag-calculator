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
    """Simulate a route going south on Autopista Central."""
    # Roughly along Ruta 5 from north to south through Santiago
    route_points = [
        (-33.350, -70.681),  # North of Quilicura
        (-33.354, -70.681),  # Near PA1
        (-33.365, -70.679),
        (-33.380, -70.677),  # Near PA2
        (-33.395, -70.673),
        (-33.410, -70.669),  # Near PB1
        (-33.425, -70.665),
        (-33.437, -70.660),  # Near PB2
        (-33.450, -70.662),
        (-33.452, -70.662),  # Near PC1
    ]
    crossed = find_portals_crossed(route_points)
    assert len(crossed) > 0
    # Should detect southbound portals
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
