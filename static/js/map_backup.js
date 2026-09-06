// Initialize Map centered around central Maharashtra (Pune region)
const map = L.map('map-container').setView([18.8000, 74.5000], 7);

// Add OpenStreetMap base tile layer
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

// Feature Groups for Map Layers
const incidentLayer = L.layerGroup().addTo(map);
const sensorLayer = L.layerGroup().addTo(map);
const teamLayer = L.layerGroup().addTo(map);
const shelterLayer = L.layerGroup().addTo(map);
const routeLayer = L.layerGroup().addTo(map);

// Custom markers colors using canvas circles
function createCircleMarker(lat, lng, color, radius = 8, tooltipText = '') {
    const marker = L.circleMarker([lat, lng], {
        radius: radius,
        fillColor: color,
        color: '#ffffff',
        weight: 1.5,
        opacity: 1,
        fillOpacity: 0.8
    });
    if (tooltipText) {
        marker.bindPopup(tooltipText);
    }
    return marker;
}

// Global layers data
let mapData = {
    incidents: [],
    sensors: [],
    teams: [],
    shelters: [],
    routes: []
};

// Fetch Map Layers data from Flask API
function loadMapLayers() {
    fetch('/api/map/layers')
        .then(response => response.json())
        .then(data => {
            mapData = data;
            drawLayers();
        });
}

function drawLayers() {
    // Clear layers first
    incidentLayer.clearLayers();
    sensorLayer.clearLayers();
    teamLayer.clearLayers();
    shelterLayer.clearLayers();
    routeLayer.clearLayers();

    // 1. Plot Incidents
    if (document.getElementById('toggle-incidents').checked) {
        mapData.incidents.forEach(inc => {
            const color = inc.severity === 'Critical' ? '#ef4444' : 
                          inc.severity === 'High' ? '#f59e0b' : 
                          inc.severity === 'Medium' ? '#3b82f6' : '#64748b';
            
            const popup = `
                <div class="p-1">
                    <h6 class="fw-bold mb-1 text-danger"><i class="fa-solid fa-fire me-1"></i>${inc.title}</h6>
                    <div class="small"><strong>Type:</strong> ${inc.disaster_type}</div>
                    <div class="small"><strong>Severity:</strong> <span class="badge bg-danger">${inc.severity}</span></div>
                    <div class="small"><strong>Status:</strong> ${inc.status}</div>
                    <div class="small mt-1 text-muted">${inc.description || ''}</div>
                </div>
            `;
            
            // Draw a slightly larger circle with pulsating feel (radius 10)
            const m = createCircleMarker(inc.latitude, inc.longitude, color, 11, popup);
            m.addTo(incidentLayer);
        });
    }

    // 2. Plot Sensors
    if (document.getElementById('toggle-sensors').checked) {
        mapData.sensors.forEach(s => {
            const color = s.status === 'Critical' ? '#dc3545' : 
                          s.status === 'Warning' ? '#ffc107' : '#0ea5e9';
                          
            const popup = `
                <div class="p-1">
                    <h6 class="fw-bold mb-1 text-info"><i class="fa-solid fa-tower-broadcast me-1"></i>${s.name}</h6>
                    <div class="small"><strong>Sensor Type:</strong> ${s.sensor_type}</div>
                    <div class="small"><strong>Value:</strong> <span class="fw-bold">${s.current_value} ${s.unit}</span></div>
                    <div class="small"><strong>Status:</strong> <span class="badge bg-secondary">${s.status}</span></div>
                </div>
            `;
            
            const m = createCircleMarker(s.latitude, s.longitude, color, 8, popup);
            m.addTo(sensorLayer);
        });
    }

    // 3. Plot Rescue Teams
    if (document.getElementById('toggle-teams').checked) {
        mapData.teams.forEach(t => {
            const color = t.status === 'Available' ? '#10b981' : '#f59e0b';
            
            const popup = `
                <div class="p-1">
                    <h6 class="fw-bold mb-1 text-primary"><i class="fa-solid fa-truck-medical me-1"></i>${t.name}</h6>
                    <div class="small"><strong>Specialization:</strong> ${t.specialization}</div>
                    <div class="small"><strong>Team Size:</strong> ${t.members_count}</div>
                    <div class="small"><strong>Status:</strong> ${t.status}</div>
                </div>
            `;
            
            const m = createCircleMarker(t.latitude, t.longitude, color, 8, popup);
            m.addTo(teamLayer);
        });
    }

    // 4. Plot Shelters
    if (document.getElementById('toggle-shelters').checked) {
        mapData.shelters.forEach(sh => {
            const color = (sh.capacity - sh.occupancy) < 50 ? '#dc3545' : '#198754';
            
            const popup = `
                <div class="p-1">
                    <h6 class="fw-bold mb-1 text-success"><i class="fa-solid fa-house-chimney-user me-1"></i>${sh.name}</h6>
                    <div class="small"><strong>Occupancy:</strong> ${sh.occupancy} / ${sh.capacity}</div>
                    <div class="small"><strong>Stock level:</strong> Food ${sh.food_stock_days} Days | Water ${sh.water_stock_days} Days</div>
                </div>
            `;
            
            const m = createCircleMarker(sh.latitude, sh.longitude, color, 9, popup);
            m.addTo(shelterLayer);
        });
    }

    // 5. Plot Evacuation Routes
    if (document.getElementById('toggle-routes').checked) {
        mapData.routes.forEach(r => {
            const color = r.status === 'Safe' ? '#198754' : 
                          r.status === 'Congested' ? '#ffc107' : '#dc3545';
                          
            const polyline = L.polyline([[r.source_lat, r.source_lng], [r.dest_lat, r.dest_lng]], {
                color: color,
                weight: 4,
                opacity: 0.75,
                dashArray: r.status === 'Blocked' ? '5, 10' : null
            });
            
            const popup = `
                <div class="p-1">
                    <h6 class="fw-bold mb-1"><i class="fa-solid fa-road me-1"></i>Evacuation Corridor</h6>
                    <div class="small"><strong>Route:</strong> ${r.name}</div>
                    <div class="small"><strong>Distance:</strong> ${r.distance_km} Km</div>
                    <div class="small"><strong>Status:</strong> <span class="badge bg-secondary">${r.status}</span></div>
                    <div class="small text-danger"><strong>Hazard:</strong> ${r.hazard_info || 'None'}</div>
                </div>
            `;
            
            polyline.bindPopup(popup);
            polyline.addTo(routeLayer);
        });
    }
}

// Attach event listeners for layer toggles
document.querySelectorAll('.layer-toggle').forEach(el => {
    el.addEventListener('change', drawLayers);
});

// Evacuation Route Calculator
let activeRoutingLine = null;
function calculateRoute() {
    const srcVal = document.getElementById('route-source').value;
    const destVal = document.getElementById('route-dest').value;

    const coords = {
        'pune': [18.5204, 73.8567],
        'mumbai': [18.9500, 72.8200],
        'kolhapur': [16.7050, 74.2433],
        'pune-shelter': [18.5300, 73.8600],
        'mumbai-shelter': [19.0000, 72.8300],
        'kolhapur-shelter': [16.7200, 74.2600]
    };

    const src = coords[srcVal];
    const dest = coords[destVal];

    if (activeRoutingLine) {
        map.removeLayer(activeRoutingLine);
    }

    // Draw active calculated route line in bright cyan
    activeRoutingLine = L.polyline([src, dest], {
        color: '#0dcaf0',
        weight: 6,
        opacity: 0.9,
        dashArray: '10, 10'
    }).addTo(map);

    // Zoom map to fit the route
    map.fitBounds(activeRoutingLine.getBounds());

    const distance = (map.distance(src, dest) / 1000).toFixed(2);
    
    // Display result panel
    const resultBox = document.getElementById('route-result');
    resultBox.classList.remove('d-none');

    // Simple hazard mock checks
    let statusText = 'Safe Corridor';
    let alertClass = 'text-success';
    
    if (srcVal === 'mumbai' && destVal === 'mumbai-shelter') {
        statusText = 'Blocked Hazard';
        alertClass = 'text-danger';
    } else if (srcVal === 'kolhapur' && destVal === 'kolhapur-shelter') {
        statusText = 'Congested Flood Flow';
        alertClass = 'text-warning';
    }

    document.getElementById('route-result-title').className = `small fw-bold ${alertClass}`;
    document.getElementById('route-result-title').innerText = statusText;
    document.getElementById('route-result-details').innerText = `Distance: ${distance} Km | Status Layer check completed.`;
}

// Initial Load
loadMapLayers();
// Poll layers every 5 seconds
setInterval(loadMapLayers, 5000);
