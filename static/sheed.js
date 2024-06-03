function getQueryParams() {
    let params = new URLSearchParams(window.location.search);
    return {
        lat: params.get('lat') || '',
        lon: params.get('lon') || '',
        name: params.get('name') || ''
    };
}

function setupWebSocket() {
    const ws = new WebSocket('wss://watershed.attack-kitten.com/ws');
    const logMessages = document.getElementById('logbox');

    ws.onopen = function () {
        console.log('WebSocket connection opened');
    };

    ws.onmessage = function (event) {
        console.log(event.data);

        if (event.data.startsWith("client_id:")) {
            const client_id = event.data.split(":")[1];
            document.getElementById('client_id').value = client_id; // set form hidden value

        } else if (event.data.startsWith("log:")) {
            document.getElementById('logbox').style.display = 'block';
            const logMessage = document.createElement('div');
            const msg = event.data.split(":")[1];
            logMessage.textContent = msg;
            logMessages.appendChild(logMessage);
            logMessages.scrollTop = logMessages.scrollHeight; // Auto-scroll to the bottom
        }
    };

    ws.onerror = function (error) {
        console.error('WebSocket error:', error);
    };

    ws.onclose = function () {
        console.log('WebSocket connection closed, retrying...');
        setTimeout(setupWebSocket, 1000); // Retry connection after 1 second
    };

    return ws;
}

window.onload = function () {
    let params = getQueryParams();
    let coordinates = `${params.lat}, ${params.lon}`;
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
        };

        fetch('/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        }).then(response => response.text())
            .then(html => {
                var responsebox = document.getElementById('responsebox');
                responsebox.innerHTML = html;
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
};