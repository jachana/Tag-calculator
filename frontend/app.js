// Santiago TAG Calculator - Frontend with Route Comparison

const API_BASE = window.location.origin;

const ROUTE_COLORS = ["#4361ee", "#e76f51", "#2d6a4f"];
const ROUTE_LABELS = ["Ruta A", "Ruta B", "Ruta C"];

// ── History (localStorage) ──────────────────────────────────────────
const HISTORY_KEY = "tag_calc_history";
const MAX_HISTORY = 20;

function getHistory() {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; }
    catch { return []; }
}

function addToHistory(value) {
    if (!value || value.length < 3) return;
    let h = getHistory().filter(v => v !== value);
    h.unshift(value);
    if (h.length > MAX_HISTORY) h = h.slice(0, MAX_HISTORY);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(h));
}

// ── Suggestions dropdown ────────────────────────────────────────────
function setupSuggestions(inputId, dropdownId) {
    const input = document.getElementById(inputId);
    const dropdown = document.getElementById(dropdownId);

    function showSuggestions() {
        const val = input.value.toLowerCase().trim();
        const history = getHistory();
        const filtered = val
            ? history.filter(h => h.toLowerCase().includes(val))
            : history;

        if (filtered.length === 0) {
            dropdown.classList.add("hidden");
            return;
        }

        dropdown.innerHTML = filtered.map(h => {
            const escaped = h.replace(/</g, "&lt;").replace(/>/g, "&gt;");
            return `<div class="suggestion-item" data-value="${escaped}">${escaped}</div>`;
        }).join("");
        dropdown.classList.remove("hidden");
    }

    function hideSuggestions() {
        // Small delay so click on item registers first
        setTimeout(() => dropdown.classList.add("hidden"), 150);
    }

    input.addEventListener("focus", showSuggestions);
    input.addEventListener("input", showSuggestions);
    input.addEventListener("blur", hideSuggestions);

    dropdown.addEventListener("mousedown", e => {
        const item = e.target.closest(".suggestion-item");
        if (item) {
            input.value = item.dataset.value;
            dropdown.classList.add("hidden");
            input.focus();
        }
    });
}

setupSuggestions("origin", "origin-suggestions");
setupSuggestions("destination", "destination-suggestions");

// ── Geolocation ─────────────────────────────────────────────────────
document.getElementById("geolocate-btn").addEventListener("click", () => {
    const btn = document.getElementById("geolocate-btn");
    if (!navigator.geolocation) {
        showError("Geolocalizacion no disponible en este navegador.");
        return;
    }
    btn.classList.add("loading");
    navigator.geolocation.getCurrentPosition(
        pos => {
            const coordStr = `${pos.coords.latitude.toFixed(6)},${pos.coords.longitude.toFixed(6)}`;
            document.getElementById("origin").value = coordStr;
            map.setView([pos.coords.latitude, pos.coords.longitude], 14);
            btn.classList.remove("loading");
        },
        () => {
            showError("No se pudo obtener tu ubicacion.");
            btn.classList.remove("loading");
        },
        { enableHighAccuracy: true, timeout: 10000 }
    );
});

// ── Swap origin / destination ───────────────────────────────────────
document.getElementById("swap-btn").addEventListener("click", () => {
    const originInput = document.getElementById("origin");
    const destInput = document.getElementById("destination");
    const tmp = originInput.value;
    originInput.value = destInput.value;
    destInput.value = tmp;
});

// ── Map setup ───────────────────────────────────────────────────────
const map = L.map("map").setView([-33.45, -70.65], 12);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 18,
}).addTo(map);

let routeLayer = L.layerGroup().addTo(map);
let portalLayer = L.layerGroup().addTo(map);
let markerLayer = L.layerGroup().addTo(map);

let clickCount = 0;
let originMarker = null;
let destMarker = null;

let selectedRouteIndex = 0;
let currentData = null;

// Set default departure time to now
const departureInput = document.getElementById("departure");
const now = new Date();
now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
departureInput.value = now.toISOString().slice(0, 16);

// Load portals
async function loadPortals() {
    try {
        const resp = await fetch(`${API_BASE}/api/highways`);
        const highways = await resp.json();
        highways.forEach(hw => {
            (hw.portals || []).filter(p => p.id && p.lat != null).forEach(portal => {
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

// Map click handler
map.on("click", function (e) {
    clickCount++;
    const latlng = e.latlng;
    const coordStr = `${latlng.lat.toFixed(6)},${latlng.lng.toFixed(6)}`;

    if (clickCount % 2 === 1) {
        if (originMarker) markerLayer.removeLayer(originMarker);
        originMarker = L.marker(latlng, { title: "Origen" }).addTo(markerLayer);
        originMarker.bindPopup("Origen").openPopup();
        document.getElementById("origin").value = coordStr;
    } else {
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

const bandNames = {
    tbfp: "Fuera de punta",
    tbp: "Punta",
    ts: "Saturacion",
};

const bandClasses = {
    tbfp: "band-tbfp",
    tbp: "band-tbp",
    ts: "band-ts",
};

// ── Main comparison ─────────────────────────────────────────────────
async function compareRoutes() {
    const origin = document.getElementById("origin").value.trim();
    const destination = document.getElementById("destination").value.trim();
    const departure = document.getElementById("departure").value;
    const vehicle = document.getElementById("vehicle").value;

    if (!origin || !destination) {
        showError("Ingresa origen y destino.");
        return;
    }

    // Save to history
    addToHistory(origin);
    addToHistory(destination);

    const btn = document.getElementById("calculate-btn");
    btn.disabled = true;
    btn.textContent = "Comparando...";
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

        const resp = await fetch(`${API_BASE}/api/compare-routes`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Error en el servidor");
        }

        const data = await resp.json();
        currentData = data;
        selectedRouteIndex = 0;
        displayComparison(data);
    } catch (e) {
        showError(e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = "Comparar Rutas";
    }
}

function displayComparison(data) {
    const results = document.getElementById("results");
    results.classList.remove("hidden");
    const container = document.getElementById("routes-container");

    if (data.routes.length === 0) {
        container.innerHTML = '<div id="no-tolls"><p>No se encontraron rutas.</p></div>';
        return;
    }

    const cheapest = data.routes[0].trip_total_clp;

    container.innerHTML = data.routes.map((r, i) => {
        const savings = r.trip_total_clp - cheapest;
        const savingsTag = i > 0 && savings > 0
            ? `<span class="savings-tag">+${formatCLP(savings)}</span>`
            : "";
        const cheapestTag = i === 0 && data.routes.length > 1
            ? '<span class="cheapest-tag">Mas barata</span>'
            : "";

        const portalRows = r.toll_estimate.portals_crossed.length > 0
            ? r.toll_estimate.portals_crossed.map(p => `
                <tr>
                    <td>${p.highway}</td>
                    <td>${p.portal_name}</td>
                    <td class="${bandClasses[p.time_band]}">${bandNames[p.time_band]}</td>
                    <td>${formatCLP(p.fee_clp)}</td>
                </tr>
            `).join("")
            : '<tr><td colspan="4" class="no-portals">Sin peajes en esta ruta</td></tr>';

        return `
        <div class="route-card ${i === selectedRouteIndex ? 'selected' : ''}"
             data-index="${i}"
             onclick="selectRoute(${i})"
             style="--route-color: ${ROUTE_COLORS[i]}">
            <div class="route-header">
                <div class="route-label">
                    <span class="route-dot" style="background: ${ROUTE_COLORS[i]}"></span>
                    ${ROUTE_LABELS[i]}
                    ${cheapestTag}${savingsTag}
                </div>
                <div class="route-total">${formatCLP(r.trip_total_clp)}</div>
            </div>
            <div class="route-meta">
                <span>${r.route.distance_km} km</span>
                <span>${Math.round(r.route.duration_min)} min</span>
                <span>TAG ${formatCLP(r.toll_estimate.total_clp)}</span>
                <span>Bencina ${formatCLP(r.fuel_estimate.cost_clp)} (${r.fuel_estimate.liters} L)</span>
            </div>
            <div class="route-portals ${i === selectedRouteIndex ? '' : 'hidden'}">
                <table class="breakdown-table">
                    <thead>
                        <tr>
                            <th>Autopista</th>
                            <th>Portico</th>
                            <th>Horario</th>
                            <th>Valor</th>
                        </tr>
                    </thead>
                    <tbody>${portalRows}</tbody>
                </table>
            </div>
        </div>
        `;
    }).join("");

    drawAllRoutes(data);
}

function selectRoute(index) {
    selectedRouteIndex = index;
    document.querySelectorAll(".route-card").forEach((card, i) => {
        card.classList.toggle("selected", i === index);
        card.querySelector(".route-portals").classList.toggle("hidden", i !== index);
    });
    drawAllRoutes(currentData);
}

function drawAllRoutes(data) {
    routeLayer.clearLayers();
    markerLayer.clearLayers();

    const order = data.routes.map((_, i) => i).sort((a, b) => {
        if (a === selectedRouteIndex) return 1;
        if (b === selectedRouteIndex) return -1;
        return a - b;
    });

    let fitBounds = null;

    order.forEach(i => {
        const r = data.routes[i];
        const decoded = decodePolyline(r.route.polyline);
        const isSelected = i === selectedRouteIndex;

        const line = L.polyline(decoded, {
            color: ROUTE_COLORS[i],
            weight: isSelected ? 6 : 3,
            opacity: isSelected ? 0.9 : 0.4,
        }).addTo(routeLayer);

        if (isSelected) {
            fitBounds = line.getBounds();
        }
    });

    const selected = data.routes[selectedRouteIndex];
    const crossedIds = new Set(selected.toll_estimate.portals_crossed.map(p => p.portal_id));
    portalLayer.eachLayer(marker => {
        if (crossedIds.has(marker.portalId)) {
            marker.setStyle({ fillColor: "#e63946", radius: 8, fillOpacity: 1 });
        } else {
            marker.setStyle({ fillColor: "#6c757d", radius: 5, fillOpacity: 0.7 });
        }
    });

    if (data.routes.length > 0) {
        const first = decodePolyline(data.routes[0].route.polyline);
        if (first.length > 0) {
            const startIcon = L.divIcon({ html: "A", className: "pin-marker pin-start", iconSize: [24, 24] });
            const endIcon = L.divIcon({ html: "B", className: "pin-marker pin-end", iconSize: [24, 24] });
            L.marker(first[0], { icon: startIcon, title: "Origen" }).addTo(markerLayer);
            L.marker(first[first.length - 1], { icon: endIcon, title: "Destino" }).addTo(markerLayer);
        }
    }

    if (fitBounds) {
        map.fitBounds(fitBounds.pad(0.1));
    }
}

// Decode OSRM encoded polyline
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
        lat += (result & 1) ? ~(result >> 1) : (result >> 1);
        shift = 0; result = 0;
        do {
            b = encoded.charCodeAt(index++) - 63;
            result |= (b & 0x1f) << shift;
            shift += 5;
        } while (b >= 0x20);
        lng += (result & 1) ? ~(result >> 1) : (result >> 1);
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

// Keyboard shortcuts
document.getElementById("destination").addEventListener("keydown", e => {
    if (e.key === "Enter") compareRoutes();
});
document.getElementById("origin").addEventListener("keydown", e => {
    if (e.key === "Enter") document.getElementById("destination").focus();
});
