from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TOLL_DATA_DIR = PROJECT_ROOT / "toll_data"

OSRM_BASE_URL = "http://router.project-osrm.org"
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"

# Geofencing: how close (meters) a route point must be to a portal to count as "crossed"
PORTAL_DETECTION_RADIUS_M = 80

# User-Agent required by Nominatim usage policy
NOMINATIM_USER_AGENT = "TagCalculator/0.1 (santiago-toll-estimator)"
