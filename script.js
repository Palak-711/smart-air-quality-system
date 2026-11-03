/*==========================================================
    SMART AIR QUALITY DASHBOARD
    Fully Synchronized & Interactive Engine
==========================================================*/

// DOM ELEMENTS
const citySelect = document.getElementById("city");
const lastUpdated = document.getElementById("lastUpdated");

const aqiValue = document.getElementById("aqiValue");
const aqiStatus = document.getElementById("aqiStatus");
const aqiTrend = document.getElementById("aqiTrend");

const pm25 = document.getElementById("pm25");
const pm10 = document.getElementById("pm10");
const temperature = document.getElementById("temperature");
const humidity = document.getElementById("humidity");

const predictionIncrease = document.getElementById("predictionIncrease");
const highestAQI = document.getElementById("highestAQI");
const lowestAQI = document.getElementById("lowestAQI");
const averageAQI = document.getElementById("averageAQI");
const trend = document.getElementById("trend");

const purifierStatus = document.getElementById("purifierStatus");
const windowStatus = document.getElementById("windowStatus");
const warningBanner = document.getElementById("warning-banner");

const riskLabel = document.getElementById("riskLabel");
const riskMeter = document.getElementById("risk-meter");

const slider = document.getElementById("aqi-slider");
const sliderValue = document.getElementById("sliderValue");
const forecastValue = document.getElementById("forecastValue");
const simulateBtn = document.getElementById("simulateBtn");

const activityLog = document.getElementById("activityLog");
const gauge = document.getElementById("aqiGauge");
const heatmapContainer = document.getElementById("heatmapContainer");
const forecastButtons = document.querySelectorAll(".graph-buttons button");

// DASHBOARD STATE
const dashboard = {
    currentAQI: 185,
    previousAQI: 176,
    city: "Delhi",
    forecastMinutes: 15,
    actualData: [],
    predictedData: [],
    todayData: [],
    logs: []
};

// AQI LEVELS DEFINITION
const AQI_LEVELS = [
    {
        min: 0, max: 50,
        status: "Good", color: "#22c55e", risk: "Low",
        purifier: "OFF", windows: "Open",
        advisory: "Air quality is good. Enjoy outdoor activities!"
    },
    {
        min: 51, max: 100,
        status: "Satisfactory", color: "#8bc34a", risk: "Moderate-Low",
        purifier: "Low Speed", windows: "Open",
        advisory: "Air quality is acceptable for public activities."
    },
    {
        min: 101, max: 200,
        status: "Moderate", color: "#facc15", risk: "Moderate",
        purifier: "Running", windows: "Closed",
        advisory: "Sensitive individuals should limit prolonged outdoor exposure."
    },
    {
        min: 201, max: 300,
        status: "Poor", color: "#fb923c", risk: "High",
        purifier: "High Speed", windows: "Closed",
        advisory: "Unhealthy air. Avoid prolonged outdoor physical exertion."
    },
    {
        min: 301, max: 500,
        status: "Severe", color: "#ef4444", risk: "Extreme",
        purifier: "Maximum", windows: "Locked",
        advisory: "Emergency health warning: Stay indoors with filtration on."
    }
];

// HELPERS
function random(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

function clamp(value, min, max) {
    return Math.max(min, Math.min(value, max));
}

function average(array) {
    if (!array.length) return 0;
    const sum = array.reduce((acc, curr) => acc + curr, 0);
    return Math.round(sum / array.length);
}

function getAQILevel(aqi) {
    return AQI_LEVELS.find(l => aqi >= l.min && aqi <= l.max) || AQI_LEVELS[AQI_LEVELS.length - 1];
}

function getTrend(current, previous) {
    if (current > previous) return "↑ Rising";
    if (current < previous) return "↓ Improving";
    return "→ Stable";
}

function currentDateTime() {
    return new Date().toLocaleString("en-IN", {
        day: "2-digit", month: "short", year: "numeric",
        hour: "2-digit", minute: "2-digit", second: "2-digit"
    });
}

// INITIALIZATION DATA
function createInitialHistory() {
    dashboard.actualData = [];
    let val = dashboard.currentAQI;
    for (let i = 0; i < 24; i++) {
        val += random(-15, 15);
        val = clamp(val, 30, 420);
        dashboard.actualData.push(val);
    }
    dashboard.todayData = [...dashboard.actualData];
}

function generatePrediction() {
    dashboard.predictedData = [];
    let last = dashboard.actualData[dashboard.actualData.length - 1] || dashboard.currentAQI;
    
    let points = dashboard.forecastMinutes === 15 ? 3 : dashboard.forecastMinutes === 30 ? 6 : 12;

    for (let i = 0; i < points; i++) {
        last += random(-8, 12);
        last = clamp(last, 25, 480);
        dashboard.predictedData.push(last);
    }
}

// CHART ENGINE
const chartCanvas = document.getElementById("aqiChart");
const aqiChart = new Chart(chartCanvas, {
    type: "line",
    data: {
        labels: [],
        datasets: [
            {
                label: "Recorded AQI",
                data: [],
                borderColor: "#4cc9f0",
                backgroundColor: "rgba(76, 201, 240, 0.15)",
                borderWidth: 3,
                tension: 0.35,
                fill: true,
                pointRadius: 4
            },
            {
                label: "AI Predicted AQI",
                data: [],
                borderColor: "#ef4444",
                borderDash: [6, 6],
                borderWidth: 3,
                tension: 0.35,
                fill: false,
                pointRadius: 4
            }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { labels: { color: "#94a3b8" } }
        },
        scales: {
            x: { ticks: { color: "#94a3b8" }, grid: { color: "#22324a" } },
            y: { ticks: { color: "#94a3b8" }, grid: { color: "#22324a" }, beginAtZero: false }
        }
    }
});

function updateChart() {
    const actualLabels = dashboard.actualData.map((_, i) => `${i + 1}:00`);
    const predictionLabels = dashboard.predictedData.map((_, i) => `+${(i + 1) * 5}m`);

    aqiChart.data.labels = [...actualLabels, ...predictionLabels];
    
    // Fill previous actual steps with null for prediction dataset alignment
    const pad = new Array(dashboard.actualData.length - 1).fill(null);
    const lastActual = dashboard.actualData[dashboard.actualData.length - 1];

    aqiChart.data.datasets[0].data = dashboard.actualData;
    aqiChart.data.datasets[1].data = [...pad, lastActual, ...dashboard.predictedData];

    aqiChart.update();
}

// SYNCHRONIZATION ENGINE
function synchronizeDashboard() {
    const level = getAQILevel(dashboard.currentAQI);

    // Live Clock
    lastUpdated.textContent = currentDateTime();

    // AQI & Gauge update
    aqiValue.textContent = dashboard.currentAQI;
    aqiStatus.textContent = level.status;
    aqiStatus.style.color = level.color;
    aqiValue.style.color = level.color;

    const diff = dashboard.currentAQI - dashboard.previousAQI;
    aqiTrend.textContent = `${diff >= 0 ? '↑' : '↓'} ${Math.abs(diff)} AQI vs prior update`;

    const gaugeAngle = (dashboard.currentAQI / 500) * 360;
    gauge.style.setProperty("--gauge-color", level.color);
    gauge.style.setProperty("--gauge-angle", `${gaugeAngle}deg`);

    // Pollutants
    pm25.textContent = Math.round(dashboard.currentAQI * 0.45);
    pm10.textContent = Math.round(dashboard.currentAQI * 0.85);
    temperature.textContent = random(22, 34) + "°C";
    humidity.textContent = random(40, 75) + "%";

    // Devices & Risk
    purifierStatus.textContent = level.purifier;
    purifierStatus.style.color = level.color;
    windowStatus.textContent = level.windows;
    windowStatus.style.color = level.windows === "Open" ? "#22c55e" : "#ef4444";

    riskLabel.textContent = level.risk;
    riskLabel.style.color = level.color;
    riskMeter.style.width = `${(dashboard.currentAQI / 500) * 100}%`;
    riskMeter.style.backgroundColor = level.color;

    warningBanner.textContent = level.advisory;
    warningBanner.style.background = level.color + "22";
    warningBanner.style.borderLeft = `4px solid ${level.color}`;

    // Summary
    const history = dashboard.todayData;
    highestAQI.textContent = Math.max(...history);
    lowestAQI.textContent = Math.min(...history);
    averageAQI.textContent = average(history);
    trend.textContent = getTrend(dashboard.currentAQI, dashboard.previousAQI);

    const shift = dashboard.predictedData.length 
        ? dashboard.predictedData[dashboard.predictedData.length - 1] - dashboard.currentAQI 
        : 0;
    predictionIncrease.textContent = `${shift >= 0 ? '+' : ''}${shift} AQI`;

    // Render Heatmap
    renderHeatmap();
}

function renderHeatmap() {
    heatmapContainer.innerHTML = "";
    dashboard.todayData.forEach((val, i) => {
        const lvl = getAQILevel(val);
        const div = document.createElement("div");
        div.style.backgroundColor = lvl.color;
        div.title = `Hour ${i + 1}: AQI ${val}`;
        heatmapContainer.appendChild(div);
    });
}

function addActivity(msg) {
    dashboard.logs.unshift({
        time: new Date().toLocaleTimeString("en-IN"),
        text: msg
    });
    if (dashboard.logs.length > 6) dashboard.logs.pop();
    
    activityLog.innerHTML = dashboard.logs
        .map(l => `<div class="activity-item"><span>[${l.time}]</span> <p>${l.text}</p></div>`)
        .join("");
}

function refreshPrediction() {
    generatePrediction();
    updateChart();
    synchronizeDashboard();
}

function applyAQI(val) {
    dashboard.previousAQI = dashboard.currentAQI;
    dashboard.currentAQI = clamp(Number(val), 0, 500);

    dashboard.actualData.push(dashboard.currentAQI);
    if (dashboard.actualData.length > 24) dashboard.actualData.shift();

    dashboard.todayData = [...dashboard.actualData];

    refreshPrediction();
}

// EVENT HANDLERS
function setupListeners() {
    // City Selector
    citySelect.addEventListener("change", (e) => {
        dashboard.city = e.target.value;
        addActivity(`City changed to ${dashboard.city}`);
        applyAQI(random(80, 260));
    });

    // Forecast Buttons
    forecastButtons.forEach(btn => {
        btn.addEventListener("click", function () {
            forecastButtons.forEach(b => b.classList.remove("active"));
            this.classList.add("active");
            dashboard.forecastMinutes = Number(this.dataset.time);
            addActivity(`Forecast window updated to +${dashboard.forecastMinutes}m`);
            refreshPrediction();
        });
    });

    // Slider & Simulation
    slider.addEventListener("input", () => {
        sliderValue.textContent = slider.value;
        const diff = slider.value - dashboard.currentAQI;
        forecastValue.textContent = `${diff >= 0 ? '+' : ''}${diff}`;
    });

    simulateBtn.addEventListener("click", () => {
        applyAQI(slider.value);
        addActivity(`Manual simulation triggered: AQI set to ${dashboard.currentAQI}`);
    });
}

// INITIALIZATION ON DOM LOAD
document.addEventListener("DOMContentLoaded", () => {
    createInitialHistory();
    setupListeners();
    refreshPrediction();
    addActivity("Dashboard system initialized successfully.");
});
