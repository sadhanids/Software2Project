'use strict'
let mymap;
let airportMarkers = new L.LayerGroup();

const airportCoords = {};

const startButton = document.getElementById('start-button');
const startScreen = document.getElementById('start-screen');
const gameScreen = document.getElementById('game-screen');
const messagesLog = document.getElementById('messages-log');

const riskPopup = document.getElementById('risk-popup');
const riskMessageElement = document.getElementById('risk-message');
const proceedButton = document.getElementById('proceed-button');
const cancelButton = document.getElementById('cancel-button');

const gameOverPopup = document.getElementById('game-over-popup');
const gameOverTitle = document.getElementById('game-over-title');
const gameOverSummary = document.getElementById('game-over-summary');
const playAgainButton = document.getElementById('play-again-button');

//message log control by this function
function logMessage(message, type = 'info') {
    const p = document.createElement('p');
    p.textContent = message;
    p.className = `message-${type}`;
    messagesLog.appendChild(p);
    messagesLog.scrollTop = messagesLog.scrollHeight;
}
//allow to javascript (brain in the browser) to talk to python code - send player action, receive game state, manage errors
async function apiCall(endpoint, method, data = {}) {
    try {
        const options = {
            method: method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (method === 'POST') {
            options.body = JSON.stringify(data);
        }

        const response = await fetch(endpoint, options);
        const json = await response.json();

        if (!response.ok) {
            logMessage(`Server Error (${endpoint}): ${json.error}`, 'error');
            return null;
        }
        return json;
    } catch (error) {
        console.error('API Call Failed:', error);
        logMessage(`Network Error: Cannot reach server for ${endpoint}`, 'error');
        return null;
    }
}


function iconFactory(type) {
    let color;
    let icon;

    switch (type) {
        case 'current':
            color = 'blue';
            icon = 'plane';
            break;
        case 'target':
            color = 'red';
            icon = 'hospital';
            break;
        case 'option_clinic':
            color = 'green';
            icon = 'medkit';
            break;
        case 'option':
        default:
            color = 'orange';
            icon = 'globe';
            break;
    }

    return L.AwesomeMarkers.icon({
        icon: icon,
        markerColor: color,
        prefix: 'fa'
    });
}
//interactive global map display and ready to receive the airport and hospital marker
function initializeLeafletMap() {
    if (mymap) {
        mymap.remove();
    }

    mymap = L.map('map').setView([20, 0], 2);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '© OpenStreetMap contributors'
    }).addTo(mymap);
    airportMarkers.addTo(mymap);
}

// Tasks of function cleanup, validation, show current and target markers and options.
function updateMap(status, options) {
    airportMarkers.clearLayers();
    const currentICAO = status.current_icao;
    const targetICAO = status.target_icao;
    let currentLocationCoordinates = airportCoords[currentICAO];
    let targetCoordinates = airportCoords[targetICAO];

    if (!currentLocationCoordinates || !targetCoordinates) {
        logMessage("Map Error: Missing coordinates for current or target airport.", 'error');
        return;
    }

    L.marker(currentLocationCoordinates, { icon: iconFactory('current') })
        .addTo(airportMarkers)
        .bindPopup(`<b>Current: ${status.current_name}</b><br>(${currentICAO})`)
        .openPopup();


    L.marker(targetCoordinates, { icon: iconFactory('target') })
        .addTo(airportMarkers)
        .bindPopup(`<b>Target Hospital: ${status.target_name}</b><br>(${targetICAO})`);


    options.forEach(option => {
        const destICAO = option.Destination_ICAO;
        const destCoords = airportCoords[destICAO];
        if (destCoords) {
            const destIsClinic = !!airportCoords[destICAO].Clinic; // Check if the destination has clinic data
            const markerType = destIsClinic ? 'option_clinic' : 'option';

            const marker = L.marker(destCoords, { icon: iconFactory(markerType) })
                .addTo(airportMarkers);


            const popupContent = `
                <b>Flight Option: ${option.Destination_Name}</b> (${destICAO})<br>
                Time: ${option.Time} min<br>
                Health Loss: ${option.Health_Loss.toFixed(2)} HP
                <button class="map-action-button" onclick="handleFlightAction('${destICAO}')">
                    Fly to ${destICAO}
                </button>
            `;
            marker.bindPopup(popupContent);
        } else {
            logMessage(`Map Warning: Missing coordinates for flight destination ${destICAO}.`, 'error');
        }
    });


    const bounds = L.latLngBounds([currentLocationCoordinates, targetCoordinates]);
    mymap.fitBounds(bounds, { padding: [50, 50] });
}

// receive the current game state from the server and update client elements (message log,action button, interactive map)to reflect latest mission and available actions.
function updateGameUI(data) {
    const status = data.status;
    const options = data.options; // Get options for action area
    const messages = data.messages || [];
    const flightOptionsDiv = document.getElementById('flight-options');


    document.getElementById('loc-name').textContent = status.current_name;
    document.getElementById('loc-icao').textContent = status.current_icao;
    document.getElementById('target-name').textContent = status.target_name;
    document.getElementById('target-icao').textContent = status.target_icao;
    document.getElementById('health-value').textContent = status.health.toFixed(2);
    document.getElementById('time-left').textContent = status.time_remaining;


    updateMap(status, options);


    flightOptionsDiv.innerHTML = '';

    if (options && options.length > 0) {
        options.forEach(option => {

        });
    } else {
        flightOptionsDiv.innerHTML += '<p>Select your next flight by clicking an airport marker on the map above.</p>';
    }


    if (status.is_clinic) {
        // Dynamic generation of the heal button within the action area
        const healButtonHTML = `
            <button id="heal-option" class="flight-option">
                🏥 Stabilize Patient at Clinic
            </button>
        `;
        flightOptionsDiv.innerHTML += healButtonHTML;

        document.getElementById('heal-option').addEventListener('click', handleHealAction);
    }


    messages.forEach(msg => logMessage(msg, msg.startsWith('🏆') || msg.startsWith('--- HEALING') ? 'success' : 'info'));


    if (data.game_over) {
        showGameOver(data.outcome);
    }
}


function showGameOver(outcome) {
    gameScreen.style.display = 'none';
    gameOverPopup.style.display = 'flex';

    if (outcome === 'SUCCESS') {
        gameOverTitle.textContent = "MISSION COMPLETE!";
        gameOverTitle.style.color = '#28a745';
        gameOverSummary.textContent = `The patient has been successfully delivered to the target hospital. Total Time: ${document.getElementById('time-left').textContent} minutes.`;
    } else if (outcome === 'LOST_HEALTH') {
        gameOverTitle.textContent = "MISSION FAILURE (Health)";
        gameOverTitle.style.color = '#dc3545';
        gameOverSummary.textContent = `The patient's health dropped to zero. Time elapsed: ${document.getElementById('time-left').textContent} minutes.`;
    } else if (outcome === 'LOST_TIME') {
        gameOverTitle.textContent = "MISSION FAILURE (Time)";
        gameOverTitle.style.color = '#dc3545';
        gameOverSummary.textContent = `The time limit was exceeded before reaching the destination.`;
    }
}

// check risk , handling a risk event - given choice before the mission continues
async function handleFlightAction(targetICAO) {
    const riskData = await apiCall('/api/risk_check', 'POST', { target_icao: targetICAO });

    if (!riskData) return;

    if (riskData.risk_found) {
        const details = riskData.risk_details;
        riskMessageElement.innerHTML = `
            Risk Type: <b>${details.name}</b><br>
            Delay: <b>+${details.time_penalty} min</b><br>
            Immediate Health Loss: <b>-${details.health_penalty.toFixed(2)} HP</b>
        `;
        proceedButton.setAttribute('data-target-icao', targetICAO);
        riskPopup.style.display = 'flex';

        if (riskData.game_over_after_risk) {
            showGameOver(riskData.current_status.outcome);
          } else {
            updateGameUI(riskData.current_status);
        }
    } else {

        const execData = await apiCall('/api/take_action', 'POST', {
            action: 'fly_execute',
            target_icao: targetICAO
        });
        if (execData) {
            updateGameUI(execData);
        }
    }
}


async function handleRiskDecision(actionType) {
    const targetICAO = proceedButton.getAttribute('data-target-icao'); // Retrieve target ICAO

    riskPopup.style.display = 'none'; // Hide popup

    const data = await apiCall('/api/take_action', 'POST', {
        action: actionType,
        target_icao: targetICAO
    });

    if (data) {
        updateGameUI(data);
    }
}

async function handleHealAction() {
    const data = await apiCall('/api/take_action', 'POST', { action: 'heal' });
    if (data) {
        updateGameUI(data);
    }
}

async function startGame(playerName, playerAge) {
    initializeLeafletMap();


    try {
        const coordData = await apiCall('/api/get_airport_coords', 'GET');
        if (coordData) {
            Object.assign(airportCoords, coordData);
            logMessage(`✅ Fetched coordinates for ${Object.keys(airportCoords).length} airports.`, 'info');
        } else {
             logMessage("🚨 FATAL: Could not fetch airport coordinates from server. Check Flask logs.", 'error');
             return;
        }
    } catch (e) {
        logMessage("🚨 FATAL: Coordinate fetch failed.", 'error');
        return;
    }


    startScreen.style.display = 'none';
    gameScreen.style.display = 'block';
    messagesLog.innerHTML = '';


    if (mymap) {
        mymap.invalidateSize();
    }


    const data = await apiCall('/api/start_game', 'POST', {
        player_name: playerName,
        player_age: playerAge
    });

    if (data) {
        updateGameUI(data);
    } else {
        startScreen.style.display = 'block';
        gameScreen.style.display = 'none';
        logMessage("Could not connect to the server or initialize game data. Check your Flask terminal for details.", 'error');
    }
}



startButton.addEventListener('click', () => {
    const playerName = document.getElementById('player-name').value.trim();
    const playerAge = document.getElementById('player-age').value.trim();


    if (!playerName || !playerAge || parseInt(playerAge) < 10) {
        alert("Please enter a valid name and age (must be 10 or older) to start the mission.");
        return;
    }

    const age = parseInt(playerAge);
    startGame(playerName, age);
});


playAgainButton.addEventListener('click', () => {

    gameOverPopup.style.display = 'none';
    startScreen.style.display = 'block';
    gameScreen.style.display = 'none';
});


proceedButton.addEventListener('click', () => handleRiskDecision('fly_execute'));
cancelButton.addEventListener('click', () => handleRiskDecision('fly_cancel'));


document.addEventListener('DOMContentLoaded', initializeLeafletMap);