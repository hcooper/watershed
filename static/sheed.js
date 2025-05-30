function getQueryParams() {
    let params = new URLSearchParams(window.location.search);
    return {
        lat: params.get('lat') || '',
        lon: params.get('lon') || '',
        name: params.get('name') || ''
    };
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

    document.querySelector('form').onsubmit = function (e) {
        e.preventDefault();

        // spinner = document.getElementsByClassName('lds-ripple')[0];
        // spinner.style.display = "block";

        const formData = new FormData(e.target);
        const data = {
            coordinates: formData.get('coordinates'),
            name: formData.get('name'),
            expand_factor: formData.get('expand_factor'),
            client_id: formData.get('client_id'),
            dem: formData.get('dem'),
            snap: formData.get('snap') ? 1 : 0,
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
                // Caltopo badly handles spaces in the kml url, even when they're encoded as %20. Instead
                // you have to double-encode the "%" as "%25".
                // let t = "https://ropewiki.com/images/d/d6/Eagle_Creek.kml?ts=1748569712807";
                let kml_url = encodeURIComponent(`${location.origin}/${data['kml']}`).replace(/%20/g, '%2520');
                // let kml_url = encodeURIComponent(`${t}`).replace(/%20/g, '%2520');
                let captopo_url = `https://caltopo.com/map.html#ll=${data['lat']},${data['lon']}&z=13&kml=${kml_url}`;

                responsebox.innerHTML = `Download: <a target="_blank" href="${location.host}/${data['kml']}">KML</a> | <a target="_blank" href="${location.host}/${data['geojson']}">GeoJSON</a>
                    <br><a target="_blank" href="${captopo_url}">Open in CalTopo</a>`;
                responsebox.style.display = 'block';
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
    });



};