"""Calculate toll fees based on portal crossings, time of day, and vehicle category."""

from __future__ import annotations

from datetime import date, datetime

from src.models import PortalCrossing, TimeBand, TollEstimate, VehicleCategory

# Chilean national holidays (feriados) — fixed-date and known variable ones.
HOLIDAYS: set[date] = {
    # 2025
    date(2025, 1, 1),    # Año Nuevo
    date(2025, 4, 18),   # Viernes Santo
    date(2025, 4, 19),   # Sábado Santo
    date(2025, 5, 1),    # Día del Trabajo
    date(2025, 5, 21),   # Día de las Glorias Navales
    date(2025, 6, 20),   # Día Nacional de los Pueblos Indígenas
    date(2025, 6, 29),   # San Pedro y San Pablo
    date(2025, 7, 16),   # Virgen del Carmen
    date(2025, 8, 15),   # Asunción de la Virgen
    date(2025, 9, 18),   # Fiestas Patrias
    date(2025, 9, 19),   # Día de las Glorias del Ejército
    date(2025, 10, 12),  # Día del Encuentro de Dos Mundos
    date(2025, 10, 31),  # Día de las Iglesias Evangélicas
    date(2025, 11, 1),   # Día de Todos los Santos
    date(2025, 12, 8),   # Inmaculada Concepción
    date(2025, 12, 25),  # Navidad
    # 2026
    date(2026, 1, 1),    # Año Nuevo
    date(2026, 4, 3),    # Viernes Santo
    date(2026, 4, 4),    # Sábado Santo
    date(2026, 5, 1),    # Día del Trabajo
    date(2026, 5, 21),   # Día de las Glorias Navales
    date(2026, 6, 21),   # Día Nacional de los Pueblos Indígenas
    date(2026, 6, 29),   # San Pedro y San Pablo
    date(2026, 7, 16),   # Virgen del Carmen
    date(2026, 8, 15),   # Asunción de la Virgen
    date(2026, 9, 18),   # Fiestas Patrias
    date(2026, 9, 19),   # Día de las Glorias del Ejército
    date(2026, 10, 12),  # Día del Encuentro de Dos Mundos
    date(2026, 10, 31),  # Día de las Iglesias Evangélicas
    date(2026, 11, 1),   # Día de Todos los Santos
    date(2026, 12, 8),   # Inmaculada Concepción
    date(2026, 12, 25),  # Navidad
}


def _is_holiday(dt: datetime) -> bool:
    return dt.date() in HOLIDAYS


def _get_time_band(dt: datetime) -> TimeBand:
    """Determine the toll time band for a given datetime.

    Schedule (based on official MOP/concession tariff bands):
    - Sundays & holidays: TBFP all day
    - Saturday 10:00-14:00: TBP
    - Mon-Fri:
        - 07:00-08:00: TBP (peak)
        - 08:00-09:00: TS  (saturation — morning)
        - 09:00-17:30: TBFP (off-peak)
        - 17:30-18:00: TBP (peak)
        - 18:00-19:30: TS  (saturation — evening)
        - 19:30-20:30: TBP (peak)
        - 20:30-07:00: TBFP (off-peak)
    """
    weekday = dt.weekday()  # 0=Monday, 6=Sunday
    t = dt.hour + dt.minute / 60.0

    # Sunday or holiday: always off-peak
    if weekday == 6 or _is_holiday(dt):
        return TimeBand.TBFP

    # Saturday: mild peak midday
    if weekday == 5:
        if 10.0 <= t < 14.0:
            return TimeBand.TBP
        return TimeBand.TBFP

    # Monday-Friday
    if 7.0 <= t < 8.0:
        return TimeBand.TBP
    if 8.0 <= t < 9.0:
        return TimeBand.TS
    if 17.5 <= t < 18.0:
        return TimeBand.TBP
    if 18.0 <= t < 19.5:
        return TimeBand.TS
    if 19.5 <= t < 20.5:
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
