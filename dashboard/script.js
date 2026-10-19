const ctx = document.getElementById('aqiChart');

// Initialize Chart with dynamic capabilities
const aqiChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: ['10:00', '10:10', '10:20', 'Now', '+15 min', '+30 min'],
        datasets: [
            {
                label: 'Actual AQI',
                data: [140, 150, 165, 185, null, null],
                borderColor: '#38BDF8',
                backgroundColor: '#38BDF8',
                tension: 0.4,
                fill: false
            },
            {
                label: 'Predicted AQI (AI)',
                data: [null, null, null, 185, 205, 225],
                borderColor: '#EF4444',
                backgroundColor: '#EF4444',
                borderDash: [5,5],
                tension: 0.4,
                fill: false
            }
        ]
    },
    options: {
        responsive: true,
        animation: {
            duration: 500
        },
        plugins: {
            legend: {
                position: 'top',
                labels: { color: '#FFFFFF', font: { family: 'Poppins' } }
            }
        },
        scales: {
            x: { ticks: { color: '#94A3B8' }, grid: { color: '#334155' } },
            y: { ticks: { color: '#94A3B8' }, grid: { color: '#334155' }, beginAtZero: false }
        }
    }
});

// DOM Elements
const slider = document.getElementById('aqi-slider');
const sliderValue = document.getElementById('slider-value');
const aqiValueDisplay = document.getElementById('aqi-value');
const pm25Display = document.getElementById('pm25-value');
const pm10Display = document.getElementById('pm10-value');
const tempDisplay = document.getElementById('temp-value');
const humidityDisplay = document.getElementById('humidity-value');
const aqiStatusDisplay = document.getElementById('aqi-status');
const aqiCard = document.querySelector('.aqi-card');
const purifierStatus = document.getElementById('purifier-status');
const windowStatus = document.getElementById('window-status');
const riskMeter = document.getElementById('risk-meter');
const warningBanner = document.getElementById('warning-banner');
const terminalLog = document.getElementById('terminal-log');
const citySelect = document.getElementById('city');
const noiseReducedDisplay = document.getElementById('noise-reduced');

// Helper function for Live Logs
function addLog(message) {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const p = document.createElement('p');
    p.textContent = `[${time}] ${message}`;
    terminalLog.prepend(p);
}

// Speech Synthesizer for AI Voice Alerts
function speakAlert(text) {
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1.0;
        window.speechSynthesis.speak(utterance);
    }
}

// Master Function to Update Dashboard & Chart Dynamically
function updateDashboard(val) {
    val = parseInt(val);
    slider.value = val;
    sliderValue.textContent = val;
    aqiValueDisplay.textContent = val;
    riskMeter.value = val > 100 ? 100 : val;

    // Proportionally scale PM2.5 and PM10 based on AQI
    const pm25 = Math.round(val * 0.4);
    const pm10 = Math.round(val * 0.65);
    pm25Display.textContent = pm25;
    pm10Display.textContent = pm10;

    // Dynamic DCAE Noise Correction percentage update
    const noiseFilteredVal = (val * 0.08).toFixed(1);
    noiseReducedDisplay.textContent = `Raw Noise Reduced: ${noiseFilteredVal}%`;

    let status = "";
    let cardColor = "";
    let advice = "";
    let bannerBg = "";
    let bannerColor = "#111827";

    if (val <= 50) {
        status = "Good 🟢";
        cardColor = "#22C55E";
        bannerBg = "#86EFAC";
        advice = "✅ Air quality is satisfactory and clean. Enjoy your outdoor activities!";
    } else if (val <= 100) {
        status = "Satisfactory 🟡";
        cardColor = "#EAB308";
        bannerBg = "#FDE047";
        advice = "⚠️ Acceptable air quality. Sensitive individuals should take minor care.";
    } else if (val <= 200) {
        status = "Moderate 🟠";
        cardColor = "#F97316";
        bannerBg = "#FDB462";
        advice = "⚠️ Air Quality is Moderate. Sensitive people should avoid prolonged outdoor activity.";
    } else if (val <= 300) {
        status = "Poor 🔴";
        cardColor = "#EF4444";
        bannerBg = "#FCA5A5";
        advice = "🚨 Poor air quality! Breathing discomfort to people on prolonged exposure.";
    } else {
        status = "Severe 💀";
        cardColor = "#991B1B";
        bannerBg = "#EF4444";
        bannerColor = "#FFFFFF";
        advice = "☠️ SEVERE ALERT! Emergency conditions. Stay indoors and keep air purifiers running!";
    }

    // Apply UI styles
    aqiStatusDisplay.textContent = status;
    aqiCard.style.borderLeftColor = cardColor;
    aqiValueDisplay.style.color = cardColor;
    warningBanner.style.background = bannerBg;
    warningBanner.style.color = bannerColor;
    warningBanner.textContent = advice;

    // Device Automation Rules
    if (val > 200) {
        purifierStatus.textContent = "🟢 ON (Auto)";
        windowStatus.textContent = "🔒 CLOSED (Auto)";
    } else {
        purifierStatus.textContent = "🔴 OFF";
        windowStatus.textContent = "🟢 OPEN";
    }

    // Dynamic Chart Update
    const baseVal = val - 40;
    aqiChart.data.datasets[0].data = [
        Math.max(20, baseVal - 30),
        Math.max(20, baseVal - 15),
        Math.max(20, baseVal - 5),
        val,
        null,
        null
    ];
    
    aqiChart.data.datasets[1].data = [
        null,
        null,
        null,
        val,
        Math.min(500, Math.round(val * 1.12)),
        Math.min(500, Math.round(val * 1.25))
    ];
    
    aqiChart.update();
}

// Slider Event Handler
let lastSpokenAQI = 185;
slider.addEventListener('input', (e) => {
    const val = e.target.value;
    updateDashboard(val);

    if (Math.abs(val - lastSpokenAQI) > 60) {
        addLog(`Sensor Calibration: AQI adjusted to ${val}`);
        if (val >= 300 && lastSpokenAQI < 300) {
            speakAlert("Warning! Severe pollution level detected. Automated air purification protocols activated.");
            addLog(`CRITICAL: Severe AQI threshold breached! Emergency defense triggered.`);
        }
        lastSpokenAQI = parseInt(val);
    }
});

// City Selector Event Handler
citySelect.addEventListener('change', (e) => {
    const city = e.target.value;
    addLog(`Switched active monitoring zone to ${city}`);
    
    let targetAQI = 185;
    let temp = "30°C";
    let humidity = "55%";

    if (city === 'Delhi') {
        targetAQI = 275;
        temp = "32°C";
        humidity = "68%";
    } else if (city === 'Faridabad') {
        targetAQI = 210;
        temp = "31°C";
        humidity = "60%";
    } else if (city === 'Gurugram') {
        targetAQI = 145;
        temp = "29°C";
        humidity = "50%";
    }

    tempDisplay.textContent = temp;
    humidityDisplay.textContent = humidity;
    updateDashboard(targetAQI);
    addLog(`Fetched ESP32 telemetry data for ${city}: AQI ${targetAQI}`);
});