"""Tests for the toll engine - portal detection and toll calculation."""

from datetime import datetime

from src.models import VehicleCategory
from src.toll_calculator import calculate_toll, _get_time_band, _is_holiday
from src.toll_engine import find_portals_crossed, _haversine_m
from src.models import TimeBand


def test_haversine_known_distance():
    """Test haversine with a known distance in Santiago."""
    # Plaza Italia to Estación Central is ~4.5km
    d = _haversine_m(-33.4372, -70.6340, -33.4520, -70.6790)
    assert 3500 < d < 5500


def test_time_band_weekday_peak():
    dt = datetime(2026, 3, 4, 7, 30)  # Wednesday 7:30am -> TBP
    assert _get_time_band(dt) == TimeBand.TBP


def test_time_band_weekday_saturation_morning():
    dt = datetime(2026, 3, 4, 8, 30)  # Wednesday 8:30am -> TS
    assert _get_time_band(dt) == TimeBand.TS


def test_time_band_weekday_saturation_evening():
    dt = datetime(2026, 3, 4, 18, 30)  # Wednesday 6:30pm -> TS
    assert _get_time_band(dt) == TimeBand.TS


def test_time_band_weekday_offpeak():
    dt = datetime(2026, 3, 4, 14, 0)  # Wednesday 2pm
    assert _get_time_band(dt) == TimeBand.TBFP


def test_time_band_sunday():
    dt = datetime(2026, 3, 8, 8, 0)  # Sunday 8am
    assert _get_time_band(dt) == TimeBand.TBFP


def test_time_band_holiday():
    """Fiestas Patrias (Sep 18) should be off-peak even on a weekday."""
    dt = datetime(2026, 9, 18, 8, 30)  # Friday 8:30am but holiday
    assert _is_holiday(dt)
    assert _get_time_band(dt) == TimeBand.TBFP


def test_time_band_saturday_peak():
    dt = datetime(2026, 3, 7, 12, 0)  # Saturday noon
    assert _get_time_band(dt) == TimeBand.TBP


def test_time_band_saturday_offpeak():
    dt = datetime(2026, 3, 7, 8, 0)  # Saturday 8am
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

    # All detected portals should be northbound (bearing ~0) since route goes north
    portal_ids = {p["portal_id"] for p in crossed}
    # Should NOT include southbound portals like PA12, PA14, PA15
    assert "ac_ns_PA12" not in portal_ids
    assert "ac_ns_PA14" not in portal_ids
    assert "ac_ns_PA15" not in portal_ids


def test_fill_between_portals():
    """When two portals are detected, all portals between them should be included.

    This is the core of the entry/exit approach: if the route enters at portal A
    and exits at portal B, all portals between A and B are charged.
    """
    # Route that passes near PA10 and PA17 on Autopista Central
    # (northbound - the points match these specific portals)
    route_points = [
        (-33.472, -70.662),   # PA10
        (-33.450, -70.660),
        (-33.430, -70.663),
        (-33.395, -70.670),
        (-33.368, -70.678),   # PA17
    ]
    crossed = find_portals_crossed(route_points)

    ac_portals = [p for p in crossed if p["highway_id"] == "autopista_central"]
    portal_ids = {p["portal_id"] for p in ac_portals}

    # PA10 and PA17 are directly detected
    assert "ac_ns_PA10" in portal_ids
    assert "ac_ns_PA17" in portal_ids

    # PA31, PA13, PA16 should be FILLED IN between PA10 and PA17
    # (these are northbound portals between PA10 and PA17)
    assert "ac_ns_PA31" in portal_ids
    assert "ac_ns_PA13" in portal_ids
    assert "ac_ns_PA16" in portal_ids


def test_parallel_street_not_detected():
    """A route on a street parallel to a highway should NOT trigger portal detections.

    Simulates a route on Av. Santa María, which runs parallel to Costanera Norte
    but ~100-150m away from the portal positions.
    """
    # Points on Av. Santa María (north bank of Mapocho), offset from CN portals
    route_points = [
        (-33.4260, -70.6310),  # Near Bellavista, but on surface ~100m from tunnel
        (-33.4250, -70.6350),
        (-33.4240, -70.6400),
        (-33.4230, -70.6450),
        (-33.4220, -70.6500),
        (-33.4210, -70.6550),
    ]
    crossed = find_portals_crossed(route_points)
    cn_portals = [p for p in crossed if p["highway_id"] == "costanera_norte"]
    # Should not detect CN portals from a parallel street
    assert len(cn_portals) == 0


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
    dt = datetime(2026, 3, 4, 7, 30)  # Peak (TBP)
    result = calculate_toll(portals, dt, VehicleCategory.CAT_4)
    assert result.total_clp == 600


def test_calculate_toll_saturation():
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
    dt = datetime(2026, 3, 4, 8, 30)  # Saturation (TS)
    result = calculate_toll(portals, dt, VehicleCategory.CAT_4)
    assert result.total_clp == 900
