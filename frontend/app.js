// Santiago TAG Calculator - Frontend

const API_BASE = window.location.origin;

// Initialize map centered on Santiago
const map = L.map("map").setView([-33.45, -70.65], 12);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 18,
}).addTo(map);

// Layer groups
let routeLayer = L.layerGroup().addTo(map);
let portalLayer = L.layerGroup().addTo(map);
let markerLayer = L.layerGroup().addTo(map);

// Map click state
let clickCount = 0;
let originMarker = null;
let destMarker = null;

// Set default departure time to now
const departureInput = document.getElementById("departure");
const now = new Date();
now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
departureInput.value = now.toISOString().slice(0, 16);

// Load and display all portals on map
async function loadPortals() {
    try {
        const resp = await fetch(`${API_BASE}/api/highways`);
        const highways = await resp.json();

        highways.forEach(hw => {
            (hw.portals || []).forEach(portal => {
                const marker = L.circleMarker([portal.lat, portal.lng], {
                    radius: 5,
                    fillColor: "#6c757d",
                    color: "#fff",
                    weight: 1.5,
                    fillOpacity: 0.7,
                });
                marker.bindTooltip(`${hw.display_name}<br>${portal.name}`, {
                    className: "portal-tooltip",
                });
                marker.portalId = portal.id;
                portalLayer.addLayer(marker);
            });
        });
    } catch (e) {
        console.warn("Could not load portal data:", e);
    }
}
loadPortals();

// Map click handler - set origin/destination
map.on("click", function (e) {
    clickCount++;
    const latlng = e.latlng;
    const coordStr = `${latlng.lat.toFixed(6)},${latlng.lng.toFixed(6)}`;

    if (clickCount % 2 === 1) {
        // Set origin
        if (originMarker) markerLayer.removeLayer(originMarker);
        originMarker = L.marker(latlng, { title: "Origen" }).addTo(markerLayer);
        originMarker.bindPopup("Origen").openPopup();
        document.getElementById("origin").value = coordStr;
    } else {
        // Set destination
        if (destMarker) markerLayer.removeLayer(destMarker);
        destMarker = L.marker(latlng, { title: "Destino" }).addTo(markerLayer);
        destMarker.bindPopup("Destino").openPopup();
        document.getElementById("destination").value = coordStr;
    }
});

// Format CLP
function formatCLP(amount) {
    return "$" + amount.toLocaleString("es-CL");
}

// Band display names
const bandNames = {
    tbfp: "Fuera de punta",
    tbp: "Punta",
    ts: "Saturación",
};

const bandClasses = {
    tbfp: "band-tbfp",
    tbp: "band-tbp",
    ts: "band-ts",
};

// Main calculation
async function calculateToll() {
    const origin = document.getElementById("origin").value.trim();
    const destination = document.getElementById("destination").value.trim();
    const departure = document.getElementById("departure").value;
    const vehicle = document.getElementById("vehicle").value;

    if (!origin || !destination) {
        showError("Ingresa origen y destino.");
        return;
    }

    const btn = document.getElementById("calculate-btn");
    btn.disabled = true;
    btn.textContent = "Calculando...";
    hideError();

    try {
        const body = {
            origin: origin,
            destination: destination,
            vehicle_category: vehicle,
        };
        if (departure) {
            body.departure_time = new Date(departure).toISOString();
        }

        const resp = await fetch(`${API_BASE}/api/estimate-toll`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Error en el servidor");
        }

        const data = await resp.json();
        displayResults(data);
    } catch (e) {
        showError(e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = "Calcular Peaje";
    }
}

function displayResults(data) {
    const results = document.getElementById("results");
    results.classList.remove("hidden");

    // Route info
    document.getElementById("total-amount").textContent = formatCLP(data.toll_estimate.total_clp);
    document.getElementById("route-distance").textContent = `${data.route.distance_km} km`;
    document.getElementById("route-duration").textContent = `${Math.round(data.route.duration_min)} min`;

    // Draw route on map
    routeLayer.clearLayers();
    const decoded = decodePolyline(data.route.polyline);
    const routeLine = L.polyline(decoded, {
        color: "#4361ee",
        weight: 5,
        opacity: 0.8,
    }).addTo(routeLayer);
    map.fitBounds(routeLine.getBounds().pad(0.1));

    // Highlight crossed portals
    const crossedIds = new Set(data.toll_estimate.portals_crossed.map(p => p.portal_id));
    portalLayer.eachLayer(marker => {
        if (crossedIds.has(marker.portalId)) {
            marker.setStyle({ fillColor: "#e63946", radius: 8, fillOpacity: 1 });
        } else {
            marker.setStyle({ fillColor: "#6c757d", radius: 5, fillOpacity: 0.7 });
        }
    });

    // Breakdown table
    const tbody = document.getElementById("breakdown-body");
    const noTolls = document.getElementById("no-tolls");
    const breakdown = document.getElementById("breakdown");

    if (data.toll_estimate.portals_crossed.length === 0) {
        breakdown.classList.add("hidden");
        noTolls.classList.remove("hidden");
    } else {
        noTolls.classList.add("hidden");
        breakdown.classList.remove("hidden");

        tbody.innerHTML = data.toll_estimate.portals_crossed
            .map(p => `
                <tr>
                    <td>${p.highway}</td>
                    <td>${p.portal_name}</td>
                    <td class="${bandClasses[p.time_band]}">${bandNames[p.time_band]}</td>
                    <td>${formatCLP(p.fee_clp)}</td>
                </tr>
            `)
            .join("");
    }

    // Add origin/destination markers if not already placed
    if (decoded.length > 0) {
        markerLayer.clearLayers();
        const startIcon = L.divIcon({ html: "🟢", className: "emoji-marker", iconSize: [20, 20] });
        const endIcon = L.divIcon({ html: "🔴", className: "emoji-marker", iconSize: [20, 20] });
        L.marker(decoded[0], { icon: startIcon, title: "Origen" }).addTo(markerLayer);
        L.marker(decoded[decoded.length - 1], { icon: endIcon, title: "Destino" }).addTo(markerLayer);
    }
}

// Decode Google/OSRM encoded polyline
function decodePolyline(encoded) {
    const points = [];
    let index = 0, lat = 0, lng = 0;

    while (index < encoded.length) {
        let b, shift = 0, result = 0;
        do {
            b = encoded.charCodeAt(index++) - 63;
            result |= (b & 0x1f) << shift;
            shift += 5;
        } while (b >= 0x20);
        const dlat = (result & 1) ? ~(result >> 1) : (result >> 1);
        lat += dlat;

        shift = 0;
        result = 0;
        do {
            b = encoded.charCodeAt(index++) - 63;
            result |= (b & 0x1f) << shift;
            shift += 5;
        } while (b >= 0x20);
        const dlng = (result & 1) ? ~(result >> 1) : (result >> 1);
        lng += dlng;

        points.push([lat / 1e5, lng / 1e5]);
    }
    return points;
}

function showError(msg) {
    const el = document.getElementById("error");
    el.textContent = msg;
    el.classList.remove("hidden");
}

function hideError() {
    document.getElementById("error").classList.add("hidden");
}

// Allow Enter key to trigger calculation
document.getElementById("destination").addEventListener("keydown", e => {
    if (e.key === "Enter") calculateToll();
});
document.getElementById("origin").addEventListener("keydown", e => {
    if (e.key === "Enter") document.getElementById("destination").focus();
});
