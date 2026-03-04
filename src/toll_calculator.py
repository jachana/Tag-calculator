"""Calculate toll fees based on portal crossings, time of day, and vehicle category."""

from __future__ import annotations

from datetime import datetime

from src.models import PortalCrossing, TimeBand, TollEstimate, VehicleCategory


def _get_time_band(dt: datetime) -> TimeBand:
    """Determine the toll time band for a given datetime.

    Simplified schedule (approximate, not portal-specific):
    - Sundays & holidays: TBFP all day
    - Mon-Fri 07:00-09:00 and 17:30-20:30: TBP (peak)
    - Mon-Fri 08:00-09:00 and 18:00-19:30: TS (saturation) on high-traffic portals
    - Everything else: TBFP (off-peak)
    - Saturday 10:00-14:00: TBP on some highways

    For MVP, we simplify to just TBFP vs TBP based on weekday rush hours.
    """
    weekday = dt.weekday()  # 0=Monday, 6=Sunday
    hour = dt.hour
    minute = dt.minute
    t = hour + minute / 60.0

    # Sunday: always off-peak
    if weekday == 6:
        return TimeBand.TBFP

    # Saturday: mild peak midday
    if weekday == 5:
        if 10.0 <= t < 14.0:
            return TimeBand.TBP
        return TimeBand.TBFP

    # Monday-Friday
    if (7.0 <= t < 9.0) or (17.5 <= t < 20.5):
        return TimeBand.TBP
    return TimeBand.TBFP


def calculate_toll(
    portals_crossed: list[dict],
    departure_time: datetime,
    vehicle_category: VehicleCategory,
) -> TollEstimate:
    """Calculate total toll from list of crossed portals."""
    time_band = _get_time_band(departure_time)
    cat_key = vehicle_category.value  # e.g. "cat_4"
    band_key = time_band.value  # e.g. "tbfp"

    crossings: list[PortalCrossing] = []
    total = 0

    for portal in portals_crossed:
        rates = portal["rates"]

        # Look up rate for this category and time band
        cat_rates = rates.get(cat_key, rates.get("cat_4", {}))
        fee = cat_rates.get(band_key, 0)
        fee_int = round(fee)

        total += fee_int
        crossings.append(
            PortalCrossing(
                highway=portal["highway"],
                portal_id=portal["portal_id"],
                portal_name=portal["portal_name"],
                time_band=time_band,
                fee_clp=fee_int,
                lat=portal["lat"],
                lng=portal["lng"],
            )
        )

    return TollEstimate(
        total_clp=total,
        portals_crossed=crossings,
    )
