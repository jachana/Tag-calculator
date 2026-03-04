# Santiago TAG Toll Estimator - Implementation Plan

## Overview

A web application that estimates toll ("TAG") fees for a given route through Santiago, Chile's urban highway system. It uses the **Google Maps Routes API** for route calculation and a **local toll database** for fee estimation, since Google's Routes API does not natively support Chilean toll passes.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Frontend (React)                   │
│  ┌───────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Map View  │  │ Route Input  │  │ Toll Summary │  │
│  │ (Google    │  │ (Origin /    │  │ (Breakdown   │  │
│  │  Maps JS)  │  │  Destination)│  │  by highway) │  │
│  └───────────┘  └──────────────┘  └──────────────┘  │
└────────────────────────┬────────────────────────────┘
                         │ REST API
┌────────────────────────┴────────────────────────────┐
│                Backend (Python / FastAPI)             │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │ Route Service│  │ Toll Engine  │  │ Data Layer│  │
│  │ (Google Maps │  │ (Portal      │  │ (Toll DB) │  │
│  │  Routes API) │  │  Intersection│  │           │  │
│  │              │  │  + Pricing)  │  │           │  │
│  └──────────────┘  └──────────────┘  └───────────┘  │
└─────────────────────────────────────────────────────┘
```

## Key Design Decisions

### Why NOT rely on Google for toll pricing
- Google Maps Routes API **does not have Chilean TollPass entries** in its enum
- Even with `extraComputations: ["TOLLS"]`, it may report toll presence but not accurate CLP prices
- Santiago's toll system has complex portal-based pricing with time-of-day bands that we must model ourselves

### Approach: Route + Portal Intersection
1. Get route polyline from Google Maps Routes API
2. Decode polyline into lat/lng points
3. Check which toll portals (gantries) the route passes through using geofencing
4. Look up the applicable rate for each portal based on: highway, direction, time of day, vehicle category
5. Sum up the total estimated toll

---

## Phase 1: Project Setup & Data Model

### 1.1 Project scaffolding
- Python backend with FastAPI
- `pyproject.toml` with dependencies: `fastapi`, `uvicorn`, `httpx`, `polyline`, `pydantic`
- Frontend: Simple HTML/JS with Google Maps JavaScript API (no framework needed initially)
- Environment config for Google Maps API key

### 1.2 Toll data model (`toll_data/`)
Define JSON data files for each highway with portal information:

```json
{
  "highway": "autopista_central",
  "display_name": "Autopista Central",
  "operator": "Sociedad Concesionaria Autopista Central S.A.",
  "axes": [
    {
      "name": "Norte-Sur",
      "direction": "north_to_south",
      "portals": [
        {
          "id": "PA1",
          "name": "Portal PA1",
          "lat": -33.XXXX,
          "lng": -70.XXXX,
          "km_start": 0.0,
          "km_end": 3.97,
          "rates": {
            "cat_1": { "tbfp": 412.57, "tbp": 825.14, "ts": 1237.71 },
            "cat_2": { "tbfp": 825.14, "tbp": 1650.28, "ts": 2475.42 }
          }
        }
      ]
    }
  ],
  "schedules": {
    "punta": ["07:00-09:00", "18:00-20:00"],
    "saturacion": ["08:00-09:00"],
    "fuera_de_punta": "default"
  }
}
```

### Santiago Urban Highways to Model

| Highway | Length | Portals | Operator |
|---------|--------|---------|----------|
| **Autopista Central** | 60.5 km | ~20 | Soc. Conc. Autopista Central |
| **Costanera Norte** | 43 km | ~15 | Soc. Conc. Costanera Norte |
| **Vespucio Norte Express** | 29 km | 17 | Soc. Conc. Vespucio Norte Express |
| **Vespucio Sur** | 23 km | 15 | Soc. Conc. Vespucio Sur |
| **Autopista Nororiente** | 21.5 km | ~6 | Soc. Conc. Autopista Nororiente |
| **Túnel San Cristóbal** | 4 km | 2 | Soc. Conc. Túnel San Cristóbal |
| **Acceso Vial AMB** | 10.3 km | ~4 | Soc. Conc. AMB |

### Santiago Urban Highways — Additional Detail

| Highway | Operator Group | Billing Platform | Tolling Type |
|---------|---------------|-----------------|--------------|
| Autopista Central | VíasChile (Abertis) | Autopase | Open (per-portal, distance-based) |
| Costanera Norte | Grupo Costanera (Atlantia/CPPIB) | Grupo Costanera | Open (per-portal, distance-based) |
| Vespucio Norte Express | VíasChile (Abertis) | Autopase | Open (per-portal, distance-based) |
| Vespucio Sur | Grupo Costanera | Grupo Costanera | Open (per-portal, distance-based) |
| Autopista Nororiente | Grupo Costanera | Grupo Costanera | Open (per-portal, distance-based) |
| Túnel San Cristóbal | VíasChile (Abertis) | Autopase | Fixed toll per crossing |
| Acceso Vial AMB | Grupo Costanera | Grupo Costanera | Open (per-portal, distance-based) |
| Vespucio Oriente (AVO I) | Sacyr/Aleática | AVO | **Closed** (entry-exit based) |

> **AVO uses a different system**: Closed tolling identifies entry and exit points and charges based on distance traveled. This needs separate logic from the open portal-by-portal system.

### Vehicle Categories

| Category | Description | Typical Multiplier |
|----------|------------|-------------------|
| **Cat 1** | Motorcycles, scooters | ~0.5x base (50% discount on some highways) |
| **Cat 4** | Autos, pickups (camionetas) | 1x (base rate) |
| **Cat 4+** | Autos/pickups with trailer | Higher multiplier |
| **Cat 2** | Buses and trucks (2 axles) | ~2x base rate |
| **Cat 3** | Buses/trucks with trailer | ~3x base rate |

> Note: Category numbering varies slightly between concessionaires. The dominant target for consumer use is Cat 4.

### Time-of-Day Bands

| Band | Spanish Name | Abbreviation | Description |
|------|-------------|-------------|-------------|
| **Off-Peak** | Tarifa Base Fuera de Punta | TBFP | Lowest rate. Low-traffic hours + ALL DAY Sundays/holidays |
| **Peak** | Tarifa Base Punta | TBP | ~2x TBFP. Morning and evening rush hours |
| **Saturation** | Tarifa de Saturación | TS | ~3x TBFP. Applied when measured speeds < 50 km/h |

**How peak hours are determined**: Concessionaires measure average speeds every 30 minutes over 4-week periods each semester. If average speed drops below 50 km/h, that slot becomes TS for the next semester. Schedules are **portal-specific and semester-specific**.

**Typical peak windows** (vary by portal):
- Mon-Fri: ~07:00-09:00 and ~17:00-21:00
- Saturday: ~08:00-10:00 and ~17:00-21:00
- Sunday/Holidays: TBFP all day

### Approximate Per-km Rates (2026, Cat 4)

| Highway | TBFP ($/km) | TBP ($/km) | TS ($/km) |
|---------|------------|-----------|----------|
| Autopista Central | ~$104 | ~$208 | ~$312 |
| Costanera Norte | ~$74-143* | ~$143-217* | ~$217* |
| Vespucio Norte | Similar | ~2x TBFP | ~3x TBFP |
| Vespucio Sur | Similar | ~2x TBFP | ~3x TBFP |

*Costanera Norte rates vary by sector (Kennedy axis vs. Oriente-Poniente axis).

### Fee Formula

```
Portal charge = Rate ($/km) × Distance associated with portal (km)
Total trip cost = SUM(portal charges for all portals crossed)
```

### Enforcement (since July 2025)
- Vehicles without TAG are charged **2x the normal toll** (Pago Tardío de Transacciones)
- Must pay within 30 days or face **1 UTM per infraction** (~$69,889 CLP)
- Repeat offenders: **5x to 15x** owed amount (capped at 20 UTM)

---

## Phase 2: Backend Core

### 2.1 Google Maps Route Service (`src/route_service.py`)
- Call Google Maps Routes API `computeRoutes` endpoint
- Request polyline in response
- Decode polyline to list of (lat, lng) coordinates
- Also request `TOLLS` in `extraComputations` for supplementary info

### 2.2 Portal Geofencing (`src/toll_engine.py`)
- For each known portal, define a detection zone (circle ~50m radius around portal coordinates)
- Walk the decoded polyline points and check proximity to each portal
- Determine direction of travel through portal (using bearing of consecutive points)
- Return ordered list of portals crossed

### 2.3 Toll Calculator (`src/toll_calculator.py`)
- Given list of portals crossed + departure time + vehicle category:
  - Determine time band (TBFP/TBP/TS) for each portal crossing
  - Look up rate from toll database
  - Apply any special rules (motorcycle discounts, monthly caps, etc.)
  - Sum total and return breakdown

### 2.4 API Endpoints (`src/api.py`)
```
POST /api/estimate-toll
{
  "origin": { "lat": -33.4489, "lng": -70.6693 },
  "destination": { "lat": -33.3964, "lng": -70.5711 },
  "departure_time": "2026-03-04T08:30:00-03:00",
  "vehicle_category": 1,
  "avoid_tolls": false
}

Response:
{
  "route": { "polyline": "...", "distance_km": 15.2, "duration_min": 22 },
  "toll_estimate": {
    "total_clp": 3250,
    "currency": "CLP",
    "portals_crossed": [
      {
        "highway": "Costanera Norte",
        "portal": "P3",
        "rate_type": "TBP",
        "fee_clp": 1450
      },
      ...
    ]
  }
}
```

---

## Phase 3: Frontend

### 3.1 Map Interface
- Google Maps JavaScript API with autocomplete for origin/destination
- Draw route on map after estimation
- Mark portal locations with custom markers
- Show toll portals crossed highlighted in a different color

### 3.2 Controls Panel
- Origin / Destination inputs with Places Autocomplete
- Departure time picker (defaults to "now")
- Vehicle category selector (dropdown)
- "Estimate Toll" button

### 3.3 Results Panel
- Total estimated toll in CLP (formatted with thousands separator)
- Breakdown table: highway, portal, time band, fee
- Route summary: distance, estimated travel time
- Option to compare with "avoid tolls" route

---

## Phase 4: Toll Data Population

### 4.1 Data Collection Strategy
Portal GPS coordinates and rates need to be collected from:
- Official highway operator websites (autopistacentral.cl, costaneranorte.cl, vespucionorte.cl, etc.)
- MOP (Ministerio de Obras Públicas) published tariff documents (PDFs)
- Google Maps satellite imagery for portal coordinate verification
- Start with the 3 most-used highways: Autopista Central, Costanera Norte, Vespucio Norte

### 4.2 Data Update Strategy
- Rates change annually (January 1st), typically by IPC adjustment (~3-4%)
- Store rate effective dates so historical estimates are possible
- Make toll data easy to update (JSON files, no hardcoded values)

---

## Phase 5: Enhancements (Future)

- **Alternative routes comparison**: Show toll cost for 2-3 route options side by side
- **Monthly cost estimator**: "If you do this commute daily, your monthly TAG bill would be ~$X"
- **No-TAG penalty estimation**: Show 2x penalty cost for vehicles without TAG (PTT system)
- **AVO (Vespucio Oriente) support**: Closed tolling system requires entry/exit logic
- **Semester schedule updates**: Tariff band assignments change every semester based on speed data
- **Rate update automation**: Scrape official concessionaire sites for annual rate changes (every Jan 1)
- **Motorcycle discount**: Automatic 50% discount for Cat 1 vehicles on applicable highways
- **Monthly cap awareness**: Some highways cap monthly charges (e.g., Costanera Norte ~$344,720/month)
- **Mobile-responsive design**

---

## Tech Stack Summary

| Component | Technology | Reason |
|-----------|-----------|--------|
| Backend | Python + FastAPI | Fast async API, great for prototyping |
| Route API | Google Maps Routes API | Best routing data, polyline support |
| Frontend Map | Google Maps JavaScript API | Integrated autocomplete + map rendering |
| Frontend UI | Vanilla HTML/CSS/JS | Minimal, no build step needed initially |
| Toll Data | JSON files | Easy to edit, version control friendly |
| Deployment | Docker (future) | Simple containerized deployment |

---

## File Structure

```
Tag-calculator/
├── PLAN.md
├── pyproject.toml
├── .env.example              # GOOGLE_MAPS_API_KEY=your_key_here
├── src/
│   ├── __init__.py
│   ├── main.py               # FastAPI app entry point
│   ├── api.py                # API route definitions
│   ├── route_service.py      # Google Maps Routes API integration
│   ├── toll_engine.py        # Portal geofencing logic
│   ├── toll_calculator.py    # Fee calculation logic
│   ├── models.py             # Pydantic models
│   └── config.py             # Settings / env config
├── toll_data/
│   ├── autopista_central.json
│   ├── costanera_norte.json
│   ├── vespucio_norte.json
│   ├── vespucio_sur.json
│   ├── autopista_nororiente.json
│   ├── tunel_san_cristobal.json
│   ├── acceso_vial_amb.json
│   └── schedules.json        # Shared time-band definitions
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── tests/
│   ├── test_toll_engine.py
│   ├── test_toll_calculator.py
│   └── test_api.py
└── README.md
```

---

## Implementation Order

1. **Phase 1**: Project setup, data model, collect portal data for Autopista Central (as proof of concept)
2. **Phase 2**: Backend — route service, toll engine, calculator, API
3. **Phase 3**: Frontend — map, controls, results display
4. **Phase 4**: Populate remaining highway data
5. **Phase 5**: Polish, testing, and enhancements

---

## References & Data Sources

### Official Concessionaire Tariff Pages
- [Autopista Central — Tarifas](https://www.autopistacentral.cl/tarifas/)
- [Costanera Norte — Tarifas](https://web.costaneranorte.cl/tarifas/)
- [Vespucio Norte — Tarifas](https://www.vespucionorte.cl/Home/Tarifas)
- [Vespucio Sur — Tarifas](https://www.vespuciosur.cl/tarifas/)
- [Autopista Nororiente — Tarifas](https://www.autopistanororiente.cl/tarifas/)
- [AVO — Vespucio Oriente](https://www.avo.cl/)

### Government Sources
- [MOP — Mapas de peajes y pórticos](https://www.mop.gob.cl/serviciosmop/mapas-de-peajes-y-porticos/)
- [Dirección General de Concesiones — Valores urbanas](https://concesiones.mop.gob.cl/peajesporticos/paginas/valores-urbanas.aspx)

### API Documentation
- [Google Maps Routes API — Compute Routes](https://developers.google.com/maps/documentation/routes/overview)
- [Google Maps Routes API — Calculate Toll Fees](https://developers.google.com/maps/documentation/routes/calculate_toll_fees)
- [Google Maps TollPass Reference](https://developers.google.com/maps/documentation/routes_preferred/reference/rest/Shared.Types/TollPass) (Chile NOT supported)

### Existing Calculators (for reference/validation)
- [PeajesChile — Calculadora TAG](https://peajeschile.com/calcular-tag/)
- [ChilePeajes](https://chilepeajes.cl/)
- [Costanera Norte — Calcula tu viaje](https://web.costaneranorte.cl/calcula-tu-viaje/)
- [Autopase — Listado de tarifas](https://www.autopase.cl/tarifa/listado)
