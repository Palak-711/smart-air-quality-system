/* ==========================================================================
   SMART AIR QUALITY DASHBOARD  -  script.js
   --------------------------------------------------------------------------
   Written against the exact ids / classes in the supplied index.html.
   Requires Chart.js v4 (already loaded by index.html before this file).

   Sections
     1.  Configuration (AQI levels, forecast options, constants)
     2.  DOM references (exact ids / classes from index.html)
     3.  Application state
     4.  Helpers (math, formatting, animation)
     5.  Helper styles (only for elements the stylesheet does not cover)
     6.  Activity log + live clock
     7.  Data generation (metrics, history, forecast)
     8.  Rendering (cards, gauge, health, devices, summary, history)
     9.  Chart.js graph
     10. Controller (apply AQI, slider, forecast buttons, simulation, city)
     11. Initialisation
   ========================================================================== */

(() => {
    'use strict';

    /* ======================================================================
       1. CONFIGURATION
       ====================================================================== */

    const MAX_LOGS = 8;          // newest log entries kept in #activityLog
    const MAX_AQI = 500;
    const STEP_MIN = 5;          // minutes between chart points
    const PAST_POINTS = 12;      // 12 x 5 min = last hour; index 12 = "Now"
    const MAX_TODAY_READINGS = 48;
    const SLIDER_LOG_DELAY = 450;

    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    const CITY_BASE_AQI = { Delhi: 185, Faridabad: 158, Gurugram: 142 };

    const FORECASTS = [
        { minutes: 15, label: '+15 min', spoken: '15 minute', rate: 0.07 },
        { minutes: 30, label: '+30 min', spoken: '30 minute', rate: 0.10 },
        { minutes: 60, label: '+1 Hour', spoken: '1 hour',    rate: 0.16 }
    ];

    /* AQI -> PM2.5 (µg/m³) breakpoints: [aqiLow, aqiHigh, pmLow, pmHigh] */
    const PM25_BREAKS = [
        [0,   50,   0,   30],
        [51,  100,  31,  60],
        [101, 200,  61,  90],
        [201, 300,  91,  120],
        [301, 400,  121, 250],
        [401, 500,  251, 380]
    ];

    const AQI_LEVELS = [
        {
            key: 'good', max: 50, label: 'Good', color: '#22c55e',
            bannerBg: '#10281a', bannerText: '#c9f7d9',
            banner: '✅ Good Air Quality',
            risk: 'Minimal',
            advice: 'Air quality is excellent. Outdoor activities are safe for everyone.',
            purifier: { text: 'OFF', cls: 'off', note: 'Air is clean - purifier on standby' },
            windows:  { text: 'Open', cls: 'open', note: 'Fresh air ventilation enabled' }
        },
        {
            key: 'satisfactory', max: 100, label: 'Satisfactory', color: '#84cc16',
            bannerBg: '#1b2a10', bannerText: '#e1f5b8',
            banner: '🙂 Satisfactory Air Quality',
            risk: 'Low',
            advice: 'Air quality is acceptable. Unusually sensitive people may notice minor breathing discomfort.',
            purifier: { text: 'Low Speed', cls: 'on', note: 'Eco purification mode active' },
            windows:  { text: 'Open', cls: 'open', note: 'Ventilation allowed - outdoor air is being monitored' }
        },
        {
            key: 'moderate', max: 200, label: 'Moderate', color: '#facc15',
            bannerBg: '#2b2610', bannerText: '#fdf1b0',
            banner: '⚠️ Moderate Air Quality',
            risk: 'Moderate',
            advice: 'Sensitive individuals should avoid prolonged outdoor exposure.',
            purifier: { text: 'Running', cls: 'on', note: 'Automatic purification enabled' },
            windows:  { text: 'Closed', cls: 'closed', note: 'Outdoor pollution protection active' }
        },
        {
            key: 'poor', max: 300, label: 'Poor', color: '#fb923c',
            bannerBg: '#2d1f13', bannerText: '#ffe5c2',
            banner: '🚨 Poor Air Quality - Limit Outdoor Exposure',
            risk: 'High',
            advice: 'Everyone may experience breathing discomfort. Avoid outdoor exercise and wear an N95 mask if you must go outside.',
            purifier: { text: 'High Speed', cls: 'on', note: 'Boosted filtration clearing indoor particles' },
            windows:  { text: 'Closed', cls: 'closed', note: 'Windows sealed against outdoor pollution' }
        },
        {
            key: 'severe', max: Infinity, label: 'Severe', color: '#ef4444',
            bannerBg: '#2d1315', bannerText: '#ffd0d0',
            banner: '🛑 Severe Air Quality - Health Alert',
            risk: 'Very High',
            advice: 'Health emergency conditions. Stay indoors, keep windows sealed and avoid all outdoor activity.',
            purifier: { text: 'Maximum', cls: 'on', note: 'Maximum filtration - turbo mode engaged' },
            windows:  { text: 'Locked', cls: 'locked', note: 'Windows locked until air quality improves' }
        }
    ];

    /* ======================================================================
       2. DOM REFERENCES  (exact ids / classes from index.html)
       ====================================================================== */

    const byId = (id) => document.getElementById(id);

    const els = {
        city:           byId('city'),
        lastUpdated:    byId('lastUpdated'),
        aqiValue:       byId('aqiValue'),
        aqiStatus:      byId('aqiStatus'),
        aqiTrend:       byId('aqiTrend'),
        pm25:           byId('pm25'),
        pm10:           byId('pm10'),
        temperature:    byId('temperature'),
        humidity:       byId('humidity'),
        predictionText: byId('predictionIncrease'),
        chartCanvas:    byId('aqiChart'),
        highest:        byId('highestAQI'),
        lowest:         byId('lowestAQI'),
        average:        byId('averageAQI'),
        trend:          byId('trend'),
        purifierStatus: byId('purifierStatus'),
        windowStatus:   byId('windowStatus'),
        banner:         byId('warning-banner'),
        riskLabel:      byId('riskLabel'),
        riskMeter:      byId('risk-meter'),
        slider:         byId('aqi-slider'),
        sliderValue:    byId('sliderValue'),
        forecastValue:  byId('forecastValue'),
        simulate:       byId('simulateBtn'),
        log:            byId('activityLog'),

        gauge:           document.querySelector('.aqi-gauge'),
        healthText:      document.querySelector('.health-text'),
        forecastButtons: Array.from(document.querySelectorAll('.graph-buttons button')),
        historyBoxes:    Array.from(document.querySelectorAll('.heatmap div'))
    };

    /* Device card parts are located relative to the exact status ids. */
    const devices = {
        purifier: deviceParts(els.purifierStatus),
        windows:  deviceParts(els.windowStatus)
    };

    function deviceParts(statusEl) {
        if (!statusEl) return { box: null, note: null };
        const card = statusEl.closest('.device-card');
        return {
            box:  statusEl.closest('.device-status'),
            note: card ? card.querySelector('p') : null
        };
    }

    /* ======================================================================
       3. APPLICATION STATE
       ====================================================================== */

    const state = {
        aqi: 185,
        yesterday: 173,
        bias: 0.95,                 // AI momentum: +1 worsening ... -1 improving
        forecastIndex: 0,
        prediction: [],             // predicted AQI values after "Now"
        actual: [],                 // PAST_POINTS + 1 values, last one = Now
        baseTime: new Date(),       // wall-clock time that "Now" refers to
        today: [],                  // today's AQI readings
        history: [],                // 30 daily AQI values (oldest first)
        levelKey: null,
        pmRatio: 1.67,
        tempOffset: -1,
        humOffset: 4,
        dragging: false,
        sliderLogTimer: null,
        simulating: false,
        simulateLabel: '',
        chart: null,
        shown: {},                  // values currently displayed (animation)
        raf: {}                     // active animation frames
    };

    /* ======================================================================
       4. HELPERS
       ====================================================================== */

    const clamp = (n, min, max) => Math.min(max, Math.max(min, n));
    const randInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
    const pad = (n) => String(n).padStart(2, '0');
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const signed = (n) => (n > 0 ? `+${n}` : String(n));

    function getLevel(aqi) {
        return AQI_LEVELS.find((level) => aqi <= level.max) || AQI_LEVELS[AQI_LEVELS.length - 1];
    }

    /* History boxes only have four CSS classes (good / moderate / poor / severe). */
    function historyClass(aqi) {
        if (aqi <= 100) return 'level-good';
        if (aqi <= 200) return 'level-moderate';
        if (aqi <= 300) return 'level-poor';
        return 'level-severe';
    }

    function formatDateTime(date) {
        let hours = date.getHours();
        const meridiem = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12 || 12;
        return `${pad(date.getDate())} ${MONTHS[date.getMonth()]} ${date.getFullYear()} • ` +
               `${pad(hours)}:${pad(date.getMinutes())}:${pad(date.getSeconds())} ${meridiem}`;
    }

    const formatClock = (date) => `${pad(date.getHours())}:${pad(date.getMinutes())}`;
    const formatLogTime = (date) =>
        `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;

    /* Smoothly animates a displayed number; applies it through `apply(value)`. */
    function animateValue(key, to, duration, apply) {
        const from = state.shown[key] === undefined ? to : state.shown[key];
        cancelAnimationFrame(state.raf[key]);

        if (!duration || from === to) {
            state.shown[key] = to;
            apply(to);
            return;
        }

        const start = performance.now();
        const step = (now) => {
            const progress = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            const value = from + (to - from) * eased;
            state.shown[key] = value;
            apply(value);
            if (progress < 1) state.raf[key] = requestAnimationFrame(step);
        };
        state.raf[key] = requestAnimationFrame(step);
    }

    function flash(element) {
        if (element && typeof element.animate === 'function') {
            element.animate(
                [{ transform: 'scale(1.35)', filter: 'brightness(1.5)' },
                 { transform: 'scale(1)',    filter: 'brightness(1)' }],
                { duration: 600, easing: 'ease-out' }
            );
        }
    }

    /* ======================================================================
       5. HELPER STYLES
       Only covers elements that exist in index.html but have no rule in
       style.css (status dots, gauge number, risk-meter colour, spinner).
       style.css itself is untouched.
       ====================================================================== */

    function injectHelperStyles() {
        const style = document.createElement('style');
        style.id = 'script-helper-styles';
        style.textContent = `
            .aqi-gauge #aqiValue {
                position: relative;
                z-index: 2;
                color: var(--text);
                font-size: 2.4rem;
                font-weight: 700;
                line-height: 1;
            }
            #risk-meter::-webkit-progress-value {
                background: var(--risk-color, #fb923c);
                border-radius: 20px;
            }
            #risk-meter::-moz-progress-bar {
                background: var(--risk-color, #fb923c);
                border-radius: 20px;
            }
            .device-status {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                font-weight: 600;
                font-size: 1.05rem;
            }
            .device-status .status-dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background: currentColor;
                box-shadow: 0 0 10px currentColor;
            }
            .device-status.on,
            .device-status.open   { color: #22c55e; }
            .device-status.off    { color: #94a3b8; }
            .device-status.closed { color: #4cc9f0; }
            .device-status.locked { color: #ef4444; }
            .history-card,
            .summary-card { flex: 1 1 auto; }
            .summary-card {
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .summary-card h2 { margin-bottom: 4px; }
            #aqiStatus, #aqiTrend, #warning-banner, #riskLabel {
                transition: color .4s ease, background-color .4s ease, border-color .4s ease;
            }
            #simulateBtn:disabled { opacity: .8; cursor: progress; }
            #simulateBtn.is-loading::before {
                content: "";
                display: inline-block;
                width: 14px;
                height: 14px;
                margin-right: 10px;
                border: 2px solid rgba(255, 255, 255, .35);
                border-top-color: #fff;
                border-radius: 50%;
                vertical-align: -2px;
                animation: script-spin .7s linear infinite;
            }
            @keyframes script-spin { to { transform: rotate(360deg); } }
        `;
        document.head.appendChild(style);
    }

    /* ======================================================================
       6. ACTIVITY LOG + LIVE CLOCK
       ====================================================================== */

    function addLog(message) {
        const line = document.createElement('p');
        line.textContent = `[${formatLogTime(new Date())}] ${message}`;
        els.log.insertBefore(line, els.log.firstChild);

        while (els.log.children.length > MAX_LOGS) {
            els.log.removeChild(els.log.lastChild);
        }
        els.log.scrollTop = 0;

        if (typeof line.animate === 'function') {
            line.animate([{ opacity: 0, transform: 'translateX(-8px)' },
                          { opacity: 1, transform: 'translateX(0)' }],
                         { duration: 350, easing: 'ease-out' });
        }
    }

    function updateClock() {
        els.lastUpdated.textContent = formatDateTime(new Date());
    }

    function startClock() {
        updateClock();
        setInterval(updateClock, 1000);
    }

    /* ======================================================================
       7. DATA GENERATION
       ====================================================================== */

    function computePM25(aqi) {
        const band = PM25_BREAKS.find((b) => aqi <= b[1]) || PM25_BREAKS[PM25_BREAKS.length - 1];
        const [aqiLow, aqiHigh, pmLow, pmHigh] = band;
        const ratio = clamp((aqi - aqiLow) / (aqiHigh - aqiLow), 0, 1);
        return Math.round(pmLow + ratio * (pmHigh - pmLow));
    }

    function computeMetrics(aqi) {
        const pm25 = computePM25(aqi);
        return {
            pm25,
            pm10: Math.round(pm25 * state.pmRatio),
            temperature: Math.round(36 - (aqi / MAX_AQI) * 10 + state.tempOffset),
            humidity: clamp(Math.round(38 + (aqi / MAX_AQI) * 35 + state.humOffset), 20, 95)
        };
    }

    /* Risk meter 0-100 (185 AQI ~ 46). */
    const computeRisk = (aqi) => clamp(Math.round(aqi / 4), 2, 100);

    function randomBias() {
        const magnitude = 0.35 + Math.random() * 0.65;
        return Math.random() < 0.55 ? magnitude : -magnitude;
    }

    function randomSimulationAqi() {
        const bands = [
            { min: 15,  max: 50,  weight: 10 },
            { min: 51,  max: 100, weight: 15 },
            { min: 101, max: 200, weight: 30 },
            { min: 201, max: 300, weight: 25 },
            { min: 301, max: 480, weight: 20 }
        ];
        const total = bands.reduce((sum, band) => sum + band.weight, 0);
        let aqi = state.aqi;

        for (let attempt = 0; attempt < 12 && Math.abs(aqi - state.aqi) < 25; attempt += 1) {
            let roll = Math.random() * total;
            const band = bands.find((b) => (roll -= b.weight) <= 0) || bands[2];
            aqi = randInt(band.min, band.max);
        }
        return aqi;
    }

    /* Last hour of actual readings, ending exactly at the current AQI. */
    function buildPastSeries(aqi) {
        const series = new Array(PAST_POINTS + 1);
        const volatility = Math.max(5, aqi * 0.045);
        let value = aqi;
        series[PAST_POINTS] = aqi;

        for (let i = PAST_POINTS - 1; i >= 0; i -= 1) {
            value = clamp(value - state.bias * aqi * 0.012 + (Math.random() - 0.5) * volatility * 1.6, 0, MAX_AQI);
            series[i] = Math.round(value);
        }
        return series;
    }

    /* Keeps the history stable while the slider moves: only the shape moves. */
    function shiftActualSeries(previousAqi, nextAqi) {
        const delta = nextAqi - previousAqi;
        for (let i = 0; i < PAST_POINTS; i += 1) {
            const weight = Math.pow(i / PAST_POINTS, 1.6);
            state.actual[i] = clamp(Math.round(state.actual[i] + delta * weight), 0, MAX_AQI);
        }
        state.actual[PAST_POINTS] = nextAqi;
    }

    /* AI prediction: rebuilt from the current AQI and the selected horizon. */
    function computePrediction() {
        const forecast = FORECASTS[state.forecastIndex];
        const steps = forecast.minutes / STEP_MIN;

        let delta = Math.round(state.aqi * forecast.rate * state.bias);
        if (delta === 0 && Math.abs(state.bias) > 0.15) delta = state.bias > 0 ? 1 : -1;
        const target = clamp(state.aqi + delta, 0, MAX_AQI);
        delta = target - state.aqi;

        const wiggleSize = Math.max(2, state.aqi * 0.012);
        const points = [];
        for (let k = 1; k <= steps; k += 1) {
            const t = k / steps;
            const eased = 1 - Math.pow(1 - t, 1.6);
            const wiggle = Math.sin(k * 1.35) * wiggleSize * (1 - t);
            points.push(k === steps ? target : clamp(Math.round(state.aqi + delta * eased + wiggle), 0, MAX_AQI));
        }
        state.prediction = points;
    }

    const getForecastDelta = () =>
        state.prediction.length ? state.prediction[state.prediction.length - 1] - state.aqi : 0;

    /* Seeds today's readings and the 30-day history from the existing HTML. */
    function seedToday(aqi) {
        const readings = [];
        for (let i = 0; i < 11; i += 1) readings.push(clamp(aqi + randInt(-35, 30), 5, MAX_AQI));
        readings.push(aqi);
        state.today = readings;
    }

    function seedHistoryFromDom() {
        const ranges = {
            'level-good':     [30, 100],
            'level-moderate': [110, 195],
            'level-poor':     [210, 290],
            'level-severe':   [310, 420]
        };
        state.history = els.historyBoxes.map((box) => {
            const cls = Object.keys(ranges).find((name) => box.classList.contains(name)) || 'level-moderate';
            return randInt(ranges[cls][0], ranges[cls][1]);
        });
    }

    function recordReading(aqi, mode) {
        if (mode === 'replace' && state.today.length) {
            state.today[state.today.length - 1] = aqi;
        } else {
            state.today.push(aqi);
            if (state.today.length > MAX_TODAY_READINGS) state.today.shift();
        }
    }

    /* ======================================================================
       8. RENDERING
       ====================================================================== */

    function setGauge(value, color) {
        const degrees = clamp((value / MAX_AQI) * 360, 8, 360);
        els.gauge.style.background =
            `conic-gradient(${color} 0deg ${degrees}deg, #23334a ${degrees}deg 360deg)`;
        els.gauge.style.boxShadow = `0 0 28px ${color}40`;
    }

    function renderAqiCard(level, duration) {
        animateValue('aqi', state.aqi, duration, (value) => {
            els.aqiValue.textContent = Math.round(value);
            setGauge(value, level.color);
        });

        els.aqiStatus.textContent = level.label;
        els.aqiStatus.style.color = level.color;

        const diff = state.aqi - state.yesterday;
        if (diff > 0) {
            els.aqiTrend.textContent = `↑ ${diff} AQI higher than yesterday`;
            els.aqiTrend.style.color = '#f87171';
        } else if (diff < 0) {
            els.aqiTrend.textContent = `↓ ${Math.abs(diff)} AQI lower than yesterday`;
            els.aqiTrend.style.color = '#4ade80';
        } else {
            els.aqiTrend.textContent = '→ Same as yesterday';
            els.aqiTrend.style.color = '#94a3b8';
        }
    }

    function renderMetrics(duration) {
        const metrics = computeMetrics(state.aqi);

        animateValue('pm25', metrics.pm25, duration, (v) => { els.pm25.textContent = Math.round(v); });
        animateValue('pm10', metrics.pm10, duration, (v) => { els.pm10.textContent = Math.round(v); });
        animateValue('temperature', metrics.temperature, duration, (v) => {
            els.temperature.textContent = `${Math.round(v)}°C`;
        });
        animateValue('humidity', metrics.humidity, duration, (v) => {
            els.humidity.textContent = `${Math.round(v)}%`;
        });
    }

    function renderHealth(level, duration) {
        els.banner.textContent = level.banner;
        els.banner.style.backgroundColor = level.bannerBg;
        els.banner.style.borderLeftColor = level.color;
        els.banner.style.color = level.bannerText;

        els.riskLabel.textContent = level.risk;
        els.riskLabel.style.color = level.color;

        if (els.healthText) els.healthText.textContent = level.advice;

        els.riskMeter.style.setProperty('--risk-color', level.color);
        animateValue('risk', computeRisk(state.aqi), duration, (value) => {
            els.riskMeter.value = value;
        });
    }

    function applyDevice(part, statusEl, config) {
        statusEl.textContent = config.text;
        if (part.box) part.box.className = `device-status ${config.cls}`;
        if (part.note) part.note.textContent = config.note;
    }

    function renderDevices(level) {
        applyDevice(devices.purifier, els.purifierStatus, level.purifier);
        applyDevice(devices.windows, els.windowStatus, level.windows);

        if (state.levelKey !== level.key) {
            state.levelKey = level.key;
            addLog(`Air Purifier set to ${level.purifier.text}`);
            addLog(`Smart Windows ${level.windows.text.toUpperCase()}`);
        }
    }

    function renderSummary() {
        const readings = state.today;
        const highest = Math.max(...readings);
        const lowest = Math.min(...readings);
        const average = Math.round(readings.reduce((sum, v) => sum + v, 0) / readings.length);

        els.highest.textContent = highest;
        els.lowest.textContent = lowest;
        els.average.textContent = average;

        const earlier = readings.slice(0, -1);
        const baseline = earlier.length
            ? earlier.reduce((sum, v) => sum + v, 0) / earlier.length
            : state.aqi;
        const diff = state.aqi - baseline;

        if (diff > 3) {
            els.trend.textContent = '↑ Worsening';
            els.trend.style.color = '#f87171';
        } else if (diff < -3) {
            els.trend.textContent = '↓ Improving';
            els.trend.style.color = '#4ade80';
        } else {
            els.trend.textContent = '→ Stable';
            els.trend.style.color = '#94a3b8';
        }
    }

    function renderForecast() {
        const delta = getForecastDelta();
        const color = delta > 0 ? '#ef4444' : delta < 0 ? '#22c55e' : '#94a3b8';
        const target = state.prediction.length ? state.prediction[state.prediction.length - 1] : state.aqi;

        els.predictionText.textContent = `${signed(delta)} AQI`;
        els.predictionText.style.color = color;
        els.predictionText.title = `Predicted AQI ${target} (${FORECASTS[state.forecastIndex].label})`;

        els.forecastValue.textContent = signed(delta);
        els.forecastValue.style.color = color;
    }

    function renderForecastButtons() {
        els.forecastButtons.forEach((button, index) => {
            button.classList.toggle('active', index === state.forecastIndex);
        });
    }

    function renderSlider() {
        els.slider.value = state.aqi;
        els.sliderValue.textContent = state.aqi;
    }

    function renderHistory() {
        els.historyBoxes.forEach((box, index) => {
            const value = state.history[index];
            const daysAgo = state.history.length - index;
            box.className = historyClass(value);
            box.title = `${daysAgo} day${daysAgo === 1 ? '' : 's'} ago: AQI ${value} (${getLevel(value).label})`;
        });
    }

    function renderAll(duration) {
        const level = getLevel(state.aqi);
        renderAqiCard(level, duration);
        renderMetrics(duration);
        renderHealth(level, duration);
        renderDevices(level);
        renderSummary();
        renderForecast();
        renderSlider();
        updateChart(duration);
    }

    /* ======================================================================
       9. CHART.JS GRAPH
       Blue line  = actual AQI, ends at "Now"
       Red dashed = AI prediction, starts at "Now"
       ====================================================================== */

    const nowMarkerPlugin = {
        id: 'nowMarker',
        beforeDatasetsDraw(chart) {
            const { ctx, chartArea, scales } = chart;
            if (!chartArea || !scales.x) return;

            const x = scales.x.getPixelForValue(PAST_POINTS);
            ctx.save();

            ctx.fillStyle = 'rgba(239, 68, 68, 0.05)';
            ctx.fillRect(x, chartArea.top, chartArea.right - x, chartArea.bottom - chartArea.top);

            ctx.setLineDash([5, 5]);
            ctx.lineWidth = 1.2;
            ctx.strokeStyle = 'rgba(148, 163, 184, 0.65)';
            ctx.beginPath();
            ctx.moveTo(x, chartArea.top);
            ctx.lineTo(x, chartArea.bottom);
            ctx.stroke();

            ctx.setLineDash([]);
            ctx.font = '600 11px Inter, sans-serif';
            ctx.fillStyle = '#94a3b8';
            ctx.textBaseline = 'top';
            ctx.textAlign = 'right';
            ctx.fillText('ACTUAL', x - 8, chartArea.top + 6);
            ctx.textAlign = 'left';
            ctx.fillText('FORECAST', x + 8, chartArea.top + 6);

            ctx.restore();
        }
    };

    function buildLabels(futureCount) {
        const labels = [];
        for (let i = -PAST_POINTS; i <= futureCount; i += 1) {
            if (i === 0) {
                labels.push('Now');
            } else {
                labels.push(formatClock(new Date(state.baseTime.getTime() + i * STEP_MIN * 60000)));
            }
        }
        return labels;
    }

    /* Y axis follows the data instead of a fixed 0-500 range. */
    function computeYRange() {
        const values = state.actual.concat(state.prediction);
        const low = Math.min(...values);
        const high = Math.max(...values);
        const padding = Math.max(15, (high - low) * 0.35);

        let min = Math.max(0, Math.floor((low - padding) / 10) * 10);
        let max = Math.ceil((high + padding) / 10) * 10;
        if (max - min < 40) max = min + 40;
        return { min, max };
    }

    function createChart() {
        if (typeof Chart === 'undefined' || !els.chartCanvas) {
            console.warn('Chart.js is not available - graph skipped.');
            return;
        }

        Chart.defaults.font.family = "'Inter', sans-serif";
        Chart.defaults.color = '#94a3b8';

        const gridColor = 'rgba(148, 163, 184, 0.10)';

        state.chart = new Chart(els.chartCanvas.getContext('2d'), {
            type: 'line',
            plugins: [nowMarkerPlugin],
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Actual AQI',
                        data: [],
                        borderColor: '#3aa6ff',
                        borderWidth: 3,
                        tension: 0.4,
                        spanGaps: false,
                        fill: true,
                        backgroundColor: (context) => {
                            const { ctx, chartArea } = context.chart;
                            if (!chartArea) return 'rgba(58, 166, 255, 0.15)';
                            const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                            gradient.addColorStop(0, 'rgba(58, 166, 255, 0.35)');
                            gradient.addColorStop(1, 'rgba(58, 166, 255, 0)');
                            return gradient;
                        },
                        pointRadius: (context) => (context.dataIndex === PAST_POINTS ? 6 : 0),
                        pointHoverRadius: 7,
                        pointBackgroundColor: '#3aa6ff',
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 2
                    },
                    {
                        label: 'AI Prediction',
                        data: [],
                        borderColor: '#ef4444',
                        borderWidth: 3,
                        borderDash: [8, 6],
                        tension: 0.4,
                        spanGaps: false,
                        fill: false,
                        pointRadius: (context) =>
                            (context.dataIndex === context.dataset.data.length - 1 ? 6 : 0),
                        pointHoverRadius: 7,
                        pointBackgroundColor: '#ef4444',
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 2
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                animation: { duration: 700, easing: 'easeOutQuart' },
                plugins: {
                    legend: {
                        position: 'top',
                        align: 'end',
                        labels: {
                            usePointStyle: true,
                            pointStyle: 'line',
                            boxWidth: 28,
                            color: '#cbd5e1',
                            font: { size: 12, weight: '500' }
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(9, 17, 29, 0.96)',
                        borderColor: '#22324a',
                        borderWidth: 1,
                        padding: 12,
                        cornerRadius: 10,
                        displayColors: true,
                        titleColor: '#f8fafc',
                        bodyColor: '#cbd5e1',
                        footerColor: '#94a3b8',
                        titleFont: { size: 13, weight: '600' },
                        bodyFont: { size: 12 },
                        footerFont: { size: 11, weight: '500' },
                        filter: (item) => !(item.datasetIndex === 1 && item.dataIndex === PAST_POINTS),
                        callbacks: {
                            title: (items) => {
                                const item = items[0];
                                const label = item.label === 'Now' ? 'Now (Live)' : item.label;
                                return item.dataIndex > PAST_POINTS ? `${label} • Forecast` : label;
                            },
                            label: (item) => {
                                const value = Math.round(item.parsed.y);
                                return ` ${item.dataset.label}: ${value}  (${getLevel(value).label})`;
                            },
                            labelColor: (item) => ({
                                borderColor: item.dataset.borderColor,
                                backgroundColor: item.dataset.borderColor,
                                borderRadius: 2
                            }),
                            footer: (items) => {
                                const forecastItem = items.find(
                                    (item) => item.datasetIndex === 1 && item.dataIndex > PAST_POINTS
                                );
                                if (!forecastItem) return '';
                                return `Change from now: ${signed(Math.round(forecastItem.parsed.y) - state.aqi)} AQI`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: gridColor },
                        border: { color: 'rgba(148, 163, 184, 0.25)' },
                        ticks: {
                            autoSkip: false,
                            maxRotation: 0,
                            color: '#94a3b8',
                            callback: function (value, index) {
                                if (index === PAST_POINTS) return 'Now';
                                return (index - PAST_POINTS) % 3 === 0 ? this.getLabelForValue(value) : '';
                            }
                        }
                    },
                    y: {
                        min: 0,
                        max: 100,
                        grid: { color: gridColor },
                        border: { display: false },
                        ticks: { color: '#94a3b8', precision: 0, maxTicksLimit: 7 },
                        title: { display: true, text: 'AQI', color: '#94a3b8', font: { size: 11, weight: '600' } }
                    }
                }
            }
        });
    }

    function updateChart(duration) {
        const chart = state.chart;
        if (!chart) return;

        const futureCount = state.prediction.length;
        const range = computeYRange();

        chart.data.labels = buildLabels(futureCount);
        /* Actual data is padded with nulls: the blue line can never enter the future. */
        chart.data.datasets[0].data = state.actual.concat(new Array(futureCount).fill(null));
        /* Prediction is padded with nulls before "Now" and starts exactly at Now. */
        chart.data.datasets[1].data = new Array(PAST_POINTS).fill(null)
            .concat([state.aqi], state.prediction);

        chart.options.scales.y.min = range.min;
        chart.options.scales.y.max = range.max;
        chart.options.animation.duration = duration || 0;

        chart.update(duration ? undefined : 'none');
    }

    /* Forecast buttons rebuild only the prediction - state.actual is not touched. */
    function updateChartPredictionOnly(duration) {
        updateChart(duration);
    }

    /* ======================================================================
       10. CONTROLLER
       ====================================================================== */

    /* Single entry point that keeps every widget synchronised with state.aqi. */
    function applyAqi(aqi, options = {}) {
        const { regenerate = false, duration = 600 } = options;
        const previous = state.aqi;

        state.aqi = clamp(Math.round(aqi), 0, MAX_AQI);

        if (regenerate) {
            state.baseTime = new Date();
            state.actual = buildPastSeries(state.aqi);
        } else {
            shiftActualSeries(previous, state.aqi);
        }

        computePrediction();
        renderAll(duration);
    }

    function describePrediction() {
        const forecast = FORECASTS[state.forecastIndex];
        return `${forecast.label}: ${signed(getForecastDelta())} AQI`;
    }

    /* ---- AQI slider ---- */

    function onSliderInput() {
        if (state.simulating) return;

        const value = Number(els.slider.value);
        const previous = state.aqi;
        if (value === previous) return;

        const direction = Math.sign(value - previous);
        state.bias = clamp(state.bias * 0.4 + direction * 0.6, -1, 1);
        if (Math.abs(state.bias) < 0.35) state.bias = direction * 0.35;

        recordReading(value, state.dragging ? 'replace' : 'push');
        state.dragging = true;

        applyAqi(value, { duration: 250 });

        clearTimeout(state.sliderLogTimer);
        state.sliderLogTimer = setTimeout(onSliderSettled, SLIDER_LOG_DELAY);
    }

    function onSliderSettled() {
        state.dragging = false;
        addLog(`AQI updated to ${state.aqi}`);
        addLog(`Prediction generated (${describePrediction()})`);
        addLog('Dashboard synchronized');
    }

    /* ---- Forecast buttons (+15 min / +30 min / +1 Hour) ---- */

    function onForecastClick(index) {
        state.forecastIndex = index;
        const forecast = FORECASTS[index];

        computePrediction();
        renderForecastButtons();
        renderForecast();
        updateChartPredictionOnly(600);

        addLog(`Forecast updated to ${forecast.label}`);
        addLog(`AI generated ${forecast.spoken} prediction (${signed(getForecastDelta())} AQI)`);
    }

    /* ---- Run Simulation ---- */

    function setSimulateLoading(isLoading) {
        els.simulate.disabled = isLoading;
        els.slider.disabled = isLoading;
        els.simulate.classList.toggle('is-loading', isLoading);
        els.simulate.textContent = isLoading ? 'Simulating...' : state.simulateLabel;
    }

    function refreshHistoryBoxes() {
        const count = randInt(3, 6);
        const indexes = new Set();
        while (indexes.size < count) indexes.add(randInt(0, state.history.length - 1));

        indexes.forEach((index) => {
            state.history[index] = clamp(state.aqi + randInt(-70, 70), 20, 420);
        });
        renderHistory();
        indexes.forEach((index) => flash(els.historyBoxes[index]));
        return count;
    }

    async function runSimulation() {
        if (state.simulating) return;

        state.simulating = true;
        clearTimeout(state.sliderLogTimer);
        state.dragging = false;
        setSimulateLoading(true);

        try {
            addLog('Simulation started');
            await sleep(700);

            const aqi = randomSimulationAqi();
            state.bias = randomBias();
            state.pmRatio = 1.5 + Math.random() * 0.4;
            state.tempOffset = randInt(-3, 3);
            state.humOffset = randInt(0, 8);
            state.yesterday = clamp(aqi + randInt(-35, 35) || 8, 0, MAX_AQI);

            recordReading(aqi, 'push');
            addLog(`AQI updated to ${aqi}`);
            applyAqi(aqi, { regenerate: true, duration: 900 });

            await sleep(500);
            addLog(`Prediction generated (${describePrediction()})`);
            const updated = refreshHistoryBoxes();
            addLog(`AQI history refreshed (${updated} days updated)`);

            await sleep(500);
            addLog('Dashboard synchronized');
            addLog(`Forecast updated: ${FORECASTS[state.forecastIndex].label} → ${signed(getForecastDelta())} AQI`);

            await sleep(300);
        } finally {
            setSimulateLoading(false);
            state.simulating = false;
        }
    }

    /* ---- City dropdown ---- */

    function onCityChange() {
        if (state.simulating) return;

        const city = els.city.value;
        const base = CITY_BASE_AQI[city] !== undefined ? CITY_BASE_AQI[city] : randInt(120, 220);
        const aqi = clamp(base + randInt(-12, 12), 0, MAX_AQI);

        clearTimeout(state.sliderLogTimer);
        state.dragging = false;
        state.bias = randomBias();
        state.yesterday = clamp(aqi + (randInt(-20, 20) || 6), 0, MAX_AQI);

        recordReading(aqi, 'push');
        addLog(`City switched to ${city}`);
        addLog(`AQI updated to ${aqi}`);
        applyAqi(aqi, { regenerate: true, duration: 800 });
        addLog('Dashboard synchronized');
    }

    /* ======================================================================
       11. INITIALISATION
       ====================================================================== */

    function missingElements() {
        const required = {
            '#city': els.city, '#lastUpdated': els.lastUpdated, '#aqiValue': els.aqiValue,
            '#aqiStatus': els.aqiStatus, '#aqiTrend': els.aqiTrend, '#pm25': els.pm25,
            '#pm10': els.pm10, '#temperature': els.temperature, '#humidity': els.humidity,
            '#predictionIncrease': els.predictionText, '#aqiChart': els.chartCanvas,
            '#highestAQI': els.highest, '#lowestAQI': els.lowest, '#averageAQI': els.average,
            '#trend': els.trend, '#purifierStatus': els.purifierStatus,
            '#windowStatus': els.windowStatus, '#warning-banner': els.banner,
            '#riskLabel': els.riskLabel, '#risk-meter': els.riskMeter,
            '#aqi-slider': els.slider, '#sliderValue': els.sliderValue,
            '#forecastValue': els.forecastValue, '#simulateBtn': els.simulate,
            '#activityLog': els.log, '.aqi-gauge': els.gauge
        };
        const missing = Object.keys(required).filter((key) => !required[key]);

        if (els.forecastButtons.length !== FORECASTS.length) missing.push('.graph-buttons button (x3)');
        if (!els.historyBoxes.length) missing.push('.heatmap div');
        return missing;
    }

    function bindEvents() {
        els.slider.addEventListener('input', onSliderInput);

        els.forecastButtons.forEach((button, index) => {
            button.addEventListener('click', () => onForecastClick(index));
        });

        els.simulate.addEventListener('click', runSimulation);
        els.city.addEventListener('change', onCityChange);
    }

    function init() {
        const missing = missingElements();
        if (missing.length) {
            console.error('Dashboard cannot start - missing elements:', missing.join(', '));
            return;
        }

        injectHelperStyles();

        /* Start from what the HTML already shows. */
        state.aqi = clamp(Math.round(Number(els.slider.value)) || 185, 0, MAX_AQI);
        state.yesterday = clamp(state.aqi - 12, 0, MAX_AQI);
        state.simulateLabel = els.simulate.textContent.trim();

        const activeIndex = els.forecastButtons.findIndex((button) => button.classList.contains('active'));
        state.forecastIndex = activeIndex >= 0 ? activeIndex : 0;

        seedHistoryFromDom();
        seedToday(state.aqi);
        renderHistory();
        renderForecastButtons();
        bindEvents();
        createChart();

        /* Replace the static placeholder log lines with real start-up entries. */
        els.log.innerHTML = '';
        addLog('Dashboard initialized');

        state.baseTime = new Date();
        state.actual = buildPastSeries(state.aqi);
        computePrediction();
        renderAll(0);

        addLog(`AQI updated to ${state.aqi}`);
        addLog(`AI generated ${FORECASTS[state.forecastIndex].spoken} prediction (${signed(getForecastDelta())} AQI)`);
        addLog('Dashboard synchronized');

        startClock();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
