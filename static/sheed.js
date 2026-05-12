function getQueryParams() {
    let params = new URLSearchParams(window.location.search);
    return {
        lat: params.get('lat') || '',
        lon: params.get('lon') || '',
        name: params.get('name') || ''
    };
}

function parseCoords(s) {
    const m = s.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (!m) return null;
    const lat = parseFloat(m[1]);
    const lon = parseFloat(m[2]);
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
    return [lat, lon];
}

let mapState = null;

function syncUrlFromCoords(coordsValue) {
    const c = parseCoords(coordsValue);
    const url = new URL(window.location);
    if (c) {
        url.searchParams.set('lat', c[0].toFixed(6));
        url.searchParams.set('lon', c[1].toFixed(6));
    } else {
        url.searchParams.delete('lat');
        url.searchParams.delete('lon');
    }
    window.history.replaceState({}, '', url);
}

function setupMap() {
    const coordsInput = document.getElementById('coordinates');
    const initial = parseCoords(coordsInput.value) || [47.6062, -122.3321];
    const initialZoom = parseCoords(coordsInput.value) ? 12 : 6;

    const map = L.map('map').setView(initial, initialZoom);
    const tfKey = document.querySelector('meta[name="thunderforest-api-key"]').content;
    L.tileLayer(`https://{s}.tile.thunderforest.com/outdoors/{z}/{x}/{y}.png?apikey=${tfKey}`, {
        maxZoom: 22,
        attribution: 'Maps © <a href="https://www.thunderforest.com">Thunderforest</a>, Data © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    const marker = L.marker(initial, { draggable: true }).addTo(map);

    let updating = false;

    function writeInput(latlng) {
        updating = true;
        coordsInput.value = `${latlng.lat.toFixed(6)}, ${latlng.lng.toFixed(6)}`;
        updating = false;
        syncUrlFromCoords(coordsInput.value);
    }

    coordsInput.addEventListener('input', function () {
        syncUrlFromCoords(coordsInput.value);
        if (updating) return;
        const c = parseCoords(coordsInput.value);
        if (!c) return;
        marker.setLatLng(c);
        map.panTo(c);
    });

    marker.on('drag', function (e) { writeInput(e.latlng); });
    marker.on('dragend', function (e) { writeInput(e.latlng); });

    map.on('click', function (e) {
        marker.setLatLng(e.latlng);
        writeInput(e.latlng);
    });

    mapState = { map, marker, watershedLayer: null };
}

function clearWatershed() {
    if (mapState && mapState.watershedLayer) {
        mapState.map.removeLayer(mapState.watershedLayer);
        mapState.watershedLayer = null;
    }
}

async function showWatershed(geojsonPath) {
    if (!mapState) return;
    const url = `${location.origin}/${encodeURI(geojsonPath)}`;
    const resp = await fetch(url);
    if (!resp.ok) {
        console.error('Failed to load watershed geojson:', resp.status);
        return;
    }
    const data = await resp.json();
    clearWatershed();
    mapState.watershedLayer = L.geoJSON(data, {
        style: { color: '#0288D1', weight: 2, fillColor: '#0288D1', fillOpacity: 0.2 }
    }).addTo(mapState.map);
    mapState.map.fitBounds(mapState.watershedLayer.getBounds(), { padding: [10, 10] });
}

function setupRopewikiSearch() {
    const coordsInput = document.getElementById('coordinates');
    const suggestionsBox = document.getElementById('coords-suggestions');
    const ropewikiLink = document.getElementById('ropewiki-link');

    let debounceTimer = null;
    let latestSearchId = 0;
    let activeIndex = -1;
    let currentResults = [];

    function hideSuggestions() {
        suggestionsBox.hidden = true;
        suggestionsBox.innerHTML = '';
        activeIndex = -1;
        currentResults = [];
    }

    function clearRopewikiLink() {
        ropewikiLink.hidden = true;
        ropewikiLink.removeAttribute('href');
        ropewikiLink.textContent = '';
    }

    function renderSuggestions(results) {
        currentResults = results;
        activeIndex = results.length ? 0 : -1;
        suggestionsBox.innerHTML = '';
        if (!results.length) {
            const empty = document.createElement('div');
            empty.className = 'suggestion-empty';
            empty.textContent = 'No matches on Ropewiki';
            suggestionsBox.appendChild(empty);
        } else {
            results.forEach((item, i) => {
                const div = document.createElement('div');
                div.className = 'suggestion' + (i === activeIndex ? ' active' : '');
                div.textContent = item.title;
                div.addEventListener('mouseenter', () => setActive(i));
                div.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    selectSuggestion(i);
                });
                suggestionsBox.appendChild(div);
            });
        }
        suggestionsBox.hidden = false;
    }

    function setActive(i) {
        const nodes = suggestionsBox.querySelectorAll('.suggestion');
        nodes.forEach((n, idx) => n.classList.toggle('active', idx === i));
        activeIndex = i;
    }

    async function selectSuggestion(i) {
        const item = currentResults[i];
        if (!item) return;
        hideSuggestions();
        try {
            const resp = await fetch('/api/ropewiki/coords?title=' + encodeURIComponent(item.title));
            if (resp.status === 404) {
                suggestionsBox.innerHTML = '';
                const msg = document.createElement('div');
                msg.className = 'suggestion-empty';
                msg.textContent = 'No coordinates on Ropewiki for "' + item.title + '"';
                suggestionsBox.appendChild(msg);
                suggestionsBox.hidden = false;
                return;
            }
            if (!resp.ok) return;
            const data = await resp.json();
            coordsInput.value = `${data.lat.toFixed(6)}, ${data.lon.toFixed(6)}`;
            coordsInput.dispatchEvent(new Event('input', { bubbles: true }));
            syncUrlFromCoords(coordsInput.value);
            document.getElementById('name').value = item.title;
            if (mapState && mapState.map) {
                mapState.map.setView([data.lat, data.lon], 13);
            }
            ropewikiLink.href = item.url;
            ropewikiLink.textContent = 'View ' + item.title + ' on Ropewiki ↗';
            ropewikiLink.hidden = false;
        } catch (err) {
            console.error('Ropewiki coords fetch failed:', err);
        }
    }

    async function runSearch(q) {
        const id = ++latestSearchId;
        try {
            const resp = await fetch('/api/ropewiki/search?q=' + encodeURIComponent(q));
            if (id !== latestSearchId) return;
            if (!resp.ok) return;
            const data = await resp.json();
            if (id !== latestSearchId) return;
            renderSuggestions(data.results || []);
        } catch (err) {
            if (id !== latestSearchId) return;
            console.error('Ropewiki search failed:', err);
        }
    }

    coordsInput.addEventListener('input', function () {
        clearRopewikiLink();
        const value = coordsInput.value;
        if (parseCoords(value)) {
            hideSuggestions();
            return;
        }
        if (value.trim().length < 2) {
            hideSuggestions();
            return;
        }
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => runSearch(value.trim()), 250);
    });

    coordsInput.addEventListener('keydown', function (e) {
        if (suggestionsBox.hidden) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (currentResults.length) setActive((activeIndex + 1) % currentResults.length);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (currentResults.length) setActive((activeIndex - 1 + currentResults.length) % currentResults.length);
        } else if (e.key === 'Enter') {
            if (activeIndex >= 0 && currentResults.length) {
                e.preventDefault();
                selectSuggestion(activeIndex);
            }
        } else if (e.key === 'Escape') {
            hideSuggestions();
        }
    });

    document.addEventListener('click', function (e) {
        if (!suggestionsBox.contains(e.target) && e.target !== coordsInput) {
            hideSuggestions();
        }
    });
}


function setupWebSocket() {
    let ws;

    if (location.protocol === 'https:') {
        ws = new WebSocket(`wss://${location.host}/ws`);
    } else {
        ws = new WebSocket(`ws://${location.host}/ws`);
    }

    attachHandlers(ws);

    function attachHandlers(ws) {
        const logMessages = document.getElementById('logbox');

        ws.onopen = function () {
            console.log('WebSocket connection opened');
        };

        ws.onmessage = function (event) {
            console.log(event.data);

            if (event.data.startsWith("client_id:")) {
                const client_id = event.data.split(":")[1];
                document.getElementById('client_id').value = client_id;

            } else if (event.data.startsWith("log:")) {
                document.getElementById('logbox').style.display = 'block';
                const logMessage = document.createElement('div');
                const msg = event.data.split(":")[1];
                logMessage.textContent = msg;
                logMessages.appendChild(logMessage);
                logMessages.scrollTop = logMessages.scrollHeight;
            }
        };

        ws.onerror = function (error) {
            console.error('WebSocket error:', error);
        };

        ws.onclose = function () {
            console.log('WebSocket connection closed, retrying...');
            setTimeout(setupWebSocket, 1000);
        };
    }
}


window.onload = function () {
    let params = getQueryParams();
    let coordinates = (params.lat && params.lon) ? `${params.lat}, ${params.lon}` : '';
    document.getElementById('coordinates').value = coordinates;
    document.getElementById('name').value = params.name;

    // Initialize WebSocket connection
    setupWebSocket();

    // Initialize Leaflet coordinate picker
    setupMap();

    // Initialize Ropewiki canyon search typeahead
    setupRopewikiSearch();

    document.querySelector('form').onsubmit = function (e) {
        e.preventDefault();

        const submitButton = document.getElementById('submitbutton');
        const originalText = submitButton.innerHTML;

        // Show spinner and disable button
        submitButton.innerHTML = '<span class="spinner"></span>Calculating...';
        submitButton.disabled = true;

        const formData = new FormData(e.target);
        const data = {
            coordinates: formData.get('coordinates'),
            name: formData.get('name'),
            expand_factor: formData.get('expand_factor'),
            client_id: formData.get('client_id'),
            dem: formData.get('dem'),
            snap: formData.get('snap') ? 1 : 0,
            snowpack: formData.get('snowpack') ? 1 : 0,
            snowpack_layer: formData.get('snowpack_layer') || 'tc',
        };

        fetch('/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        }).then(response => response.json())
            .then(data => {
                var responsebox = document.getElementById('responsebox');

                let sentinels = data['sentinels'] || [];
                let sentinelHtml = sentinels.length === 0 ? '' : `
                    <br><b>Sentinel imagery:</b><br>
                    <div style="display: flex; flex-wrap: wrap; gap: 10px; padding: 10px 0;">
                        ${sentinels.map(s => `
                            <div style="text-align: center;">
                                <div>${s.date} (-${s.days_ago}d)</div>
                                <a target="_blank" href="${location.origin}/${encodeURI(s.path)}">
                                    <img src="${location.origin}/${encodeURI(s.path)}" alt="${s.date}" style="max-width: 220px; max-height: 220px;">
                                </a>
                            </div>
                        `).join('')}
                    </div>`;

                let kml_url = `${location.origin}/${data['kml']}`;
                let caltopo_url = `https://caltopo.com/map.html#ll=${data['lat']},${data['lon']}&z=13&b=mbt&kml=${kml_url}`;

                responsebox.innerHTML = `<b>Download:</b><br>
                    <a target="_blank" href="${location.origin}/${data['kml']}">
                    <img src="static/kml.png" width="60px" alt="kml" style="padding: 10px;"></a>
                        <a target="_blank" href="${location.origin}/${data['geojson']}">
                    <img src="static/geojson.png" width="60px"  style="padding: 10px;"alt="geojson"></a>
                    <br>
                    <a class="button-link" target="_blank" href="${caltopo_url}">Open in CalTopo</a>
                    ${sentinelHtml}
                    `;
                responsebox.style.display = 'block';

                showWatershed(data['geojson']);
            })
            .catch(error => {
                console.error('Error:', error);
            })
            .finally(() => {
                // Restore button state
                submitButton.innerHTML = originalText;
                submitButton.disabled = false;
            });
    };

    document.getElementById('toggle-advanced').addEventListener('click', function (event) {
        event.preventDefault();
        var advancedSection = document.getElementById('advanced-section');
        if (advancedSection.classList.contains('expanded')) {
            advancedSection.classList.remove('expanded');
            this.textContent = 'More Options';
        } else {
            advancedSection.classList.add('expanded');
            this.textContent = 'Fewer Options';
        }
    });

    document.getElementById('submitbutton').addEventListener('click', function (event) {
        var responsebox = document.getElementById('responsebox');
        responsebox.innerHTML = "";
        responsebox.style.display = 'none';
        clearWatershed();
    });

    // Update expand factor value display
    document.getElementById('expand_factor').addEventListener('input', function (event) {
        document.getElementById('expand_factor_value').textContent = event.target.value;
    });

    // Enable/disable the snowpack band dropdown based on the snowpack checkbox
    document.getElementById('snowpack').addEventListener('change', function (event) {
        document.getElementById('snowpack_layer').disabled = !event.target.checked;
    });



};
