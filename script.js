/*==========================================================
    SMART AIR QUALITY DASHBOARD
    Part 1
    Variables, Dashboard State & Chart Initialization
==========================================================*/


//==========================================================
// DOM ELEMENTS
//==========================================================

const city = document.getElementById("city");
const lastUpdated = document.getElementById("lastUpdated");

const aqiValue = document.getElementById("aqiValue");
const aqiStatus = document.getElementById("aqiStatus");
const aqiTrend = document.getElementById("aqiTrend");

const pm25 = document.getElementById("pm25");
const pm10 = document.getElementById("pm10");
const temperature = document.getElementById("temperature");
const humidity = document.getElementById("humidity");

const predictionIncrease =
document.getElementById("predictionIncrease");

const highestAQI =
document.getElementById("highestAQI");

const lowestAQI =
document.getElementById("lowestAQI");

const averageAQI =
document.getElementById("averageAQI");

const trend =
document.getElementById("trend");

const purifierStatus =
document.getElementById("purifierStatus");

const windowStatus =
document.getElementById("windowStatus");

const warningBanner =
document.getElementById("warning-banner");

const riskLabel =
document.getElementById("riskLabel");

const riskMeter =
document.getElementById("risk-meter");

const slider =
document.getElementById("aqi-slider");

const sliderValue =
document.getElementById("sliderValue");

const forecastValue =
document.getElementById("forecastValue");

const simulateBtn =
document.getElementById("simulateBtn");

const activityLog =
document.getElementById("activityLog");

const gauge =
document.querySelector(".aqi-gauge");

const historyBoxes =
document.querySelectorAll(".heatmap div");

const forecastButtons =
document.querySelectorAll(".graph-buttons button");


//==========================================================
// DASHBOARD STATE
//==========================================================

const dashboard={

    currentAQI:185,

    previousAQI:176,

    city:"Delhi",

    forecastMinutes:15,

    actualData:[],

    predictedData:[],

    todayData:[],

    logs:[]

};


//==========================================================
// AQI LEVELS
//==========================================================

const AQI_LEVELS=[

{

min:0,
max:50,

status:"Good",

color:"#2ecc71",

risk:"Low",

purifier:"OFF",

windows:"Open",

advisory:
"Excellent air quality. Outdoor activities are completely safe."

},

{

min:51,
max:100,

status:"Satisfactory",

color:"#8BC34A",

risk:"Low",

purifier:"Low Speed",

windows:"Open",

advisory:
"Air quality is acceptable for most people."

},

{

min:101,
max:200,

status:"Moderate",

color:"#f1c40f",

risk:"Moderate",

purifier:"Running",

windows:"Closed",

advisory:
"Sensitive groups should avoid prolonged outdoor exposure."

},

{

min:201,
max:300,

status:"Poor",

color:"#e67e22",

risk:"High",

purifier:"High Speed",

windows:"Closed",

advisory:
"Everyone should reduce outdoor activity."

},

{

min:301,
max:500,

status:"Severe",

color:"#e74c3c",

risk:"Extreme",

purifier:"Maximum",

windows:"Locked",

advisory:
"Remain indoors. Avoid outdoor exposure."

}

];



//==========================================================
// HELPER FUNCTIONS
//==========================================================

function random(min,max){

return Math.floor(
Math.random()*(max-min+1)
)+min;

}


function clamp(value,min,max){

return Math.max(
min,
Math.min(value,max)
);

}


function average(array){

let sum=0;

array.forEach(num=>sum+=num);

return Math.round(sum/array.length);

}


function getAQILevel(aqi){

return AQI_LEVELS.find(level=>

aqi>=level.min &&

aqi<=level.max

);

}



function getTrend(current,previous){

if(current>previous)

return "↑ Rising";

if(current<previous)

return "↓ Improving";

return "→ Stable";

}



function currentDateTime(){

return new Date().toLocaleString(

"en-IN",

{

day:"2-digit",

month:"short",

year:"numeric",

hour:"2-digit",

minute:"2-digit",

second:"2-digit"

}

);

}



//==========================================================
// GENERATE INITIAL AQI HISTORY
//==========================================================

function createInitialHistory(){

dashboard.actualData=[];

dashboard.todayData=[];

let value=dashboard.currentAQI;


for(let i=0;i<24;i++){

value+=random(-12,10);

value=clamp(value,30,420);

dashboard.actualData.push(value);

}


dashboard.todayData=[

...dashboard.actualData

];

}



//==========================================================
// GENERATE AI PREDICTION
//==========================================================

function generatePrediction(){

dashboard.predictedData=[];

let last=

dashboard.actualData[
dashboard.actualData.length-1
];


let points;

switch(dashboard.forecastMinutes){

case 15:

points=3;

break;

case 30:

points=6;

break;

default:

points=12;

}


for(let i=0;i<points;i++){

last+=random(-8,10);

last=clamp(last,25,450);

dashboard.predictedData.push(last);

}

}



//==========================================================
// CHART.JS INITIALIZATION
//==========================================================

const chartCanvas=

document.getElementById("aqiChart");


const aqiChart=

new Chart(chartCanvas,{

type:"line",

data:{

labels:[],

datasets:[

{

label:"Actual AQI",

data:[],

borderColor:"#3498db",

backgroundColor:"rgba(52,152,219,.15)",

borderWidth:3,

tension:.35,

fill:true,

pointRadius:4,

pointHoverRadius:6

},

{

label:"AI Prediction",

data:[],

borderColor:"#e74c3c",

borderDash:[8,6],

borderWidth:3,

fill:false,

pointRadius:4,

pointHoverRadius:6,

tension:.35

}

]

},

options:{

responsive:true,

maintainAspectRatio:false,

interaction:{

mode:"index",

intersect:false

},

plugins:{

legend:{

display:true,

position:"top"

}

},

scales:{

y:{

beginAtZero:false

}

}

}

});

/*==========================================================
    SMART AIR QUALITY DASHBOARD
    Part 2A
    Dashboard Synchronization Engine
==========================================================*/



//==========================================================
// ACTIVITY LOG
//==========================================================

function addActivity(message){

    dashboard.logs.unshift({

        time:new Date().toLocaleTimeString("en-IN"),

        text:message

    });

    if(dashboard.logs.length>8){

        dashboard.logs.pop();

    }

    renderActivityLog();

}



function renderActivityLog(){

    activityLog.innerHTML="";

    dashboard.logs.forEach(log=>{

        const item=document.createElement("div");

        item.className="activity-item";

        item.innerHTML=

        `<span>${log.time}</span>
         <p>${log.text}</p>`;

        activityLog.appendChild(item);

    });

}



//==========================================================
// LIVE CLOCK
//==========================================================

function updateClock(){

    lastUpdated.textContent=currentDateTime();

}



//==========================================================
// AQI SUMMARY CARD
//==========================================================

function updateAQICard(){

    const level=getAQILevel(

        dashboard.currentAQI

    );

    aqiValue.textContent=

    dashboard.currentAQI;

    aqiStatus.textContent=

    level.status;

    aqiTrend.textContent=

    getTrend(

        dashboard.currentAQI,

        dashboard.previousAQI

    );

    aqiStatus.style.color=

    level.color;

    aqiValue.style.color=

    level.color;

    if(gauge){

        gauge.style.setProperty(

            "--gauge",

            dashboard.currentAQI

        );

    }

}



//==========================================================
// POLLUTANT CARDS
//==========================================================

function updatePollutants(){

    pm25.textContent=

    random(40,160);

    pm10.textContent=

    random(70,220);

    temperature.textContent=

    random(20,38)+"°C";

    humidity.textContent=

    random(30,90)+"%";

}



//==========================================================
// HEALTH RISK METER
//==========================================================

function updateHealthRisk(){

    const level=

    getAQILevel(

        dashboard.currentAQI

    );

    riskLabel.textContent=

    level.risk;

    if(riskMeter){

        riskMeter.style.width=

        (dashboard.currentAQI/500)*100+"%";

        riskMeter.style.background=

        level.color;

    }

}



//==========================================================
// SMART DEVICE STATUS
//==========================================================

function updateSmartDevices(){

    const level=

    getAQILevel(

        dashboard.currentAQI

    );

    purifierStatus.textContent=

    level.purifier;

    windowStatus.textContent=

    level.windows;

}



//==========================================================
// WARNING BANNER
//==========================================================

function updateHealthAdvisory(){

    const level=

    getAQILevel(

        dashboard.currentAQI

    );

    if(warningBanner){

        warningBanner.textContent=

        level.advisory;

        warningBanner.style.background=

        level.color;

    }

}



//==========================================================
// DASHBOARD SUMMARY
//==========================================================

function updateSummary(){

    const history=

    dashboard.todayData;

    const highest=

    Math.max(...history);

    const lowest=

    Math.min(...history);

    const avg=

    average(history);

    highestAQI.textContent=

    highest;

    lowestAQI.textContent=

    lowest;

    averageAQI.textContent=

    avg;

    predictionIncrease.textContent=

    dashboard.predictedData.length

    ? dashboard.predictedData[

        dashboard.predictedData.length-1

      ]-dashboard.currentAQI

    :0;

    trend.textContent=

    getTrend(

        dashboard.currentAQI,

        dashboard.previousAQI

    );

}



//==========================================================
// HISTORY HEATMAP
//==========================================================

function updateHistory(){

    if(!historyBoxes.length) return;

    historyBoxes.forEach((box,index)=>{

        const value=

        dashboard.todayData[index]||

        dashboard.currentAQI;

        const level=

        getAQILevel(value);

        box.style.background=

        level.color;

        box.title=

        "AQI : "+value;

    });

}



//==========================================================
// COMPLETE DASHBOARD SYNCHRONIZATION
//==========================================================

function synchronizeDashboard(){

    updateClock();

    updateAQICard();

    updatePollutants();

    updateHealthRisk();

    updateSmartDevices();

    updateHealthAdvisory();

    updateSummary();

    updateHistory();

    renderActivityLog();

}

/*==========================================================
    SMART AIR QUALITY DASHBOARD
    Part 2B
    Chart Engine, Forecast Controls & Simulation
==========================================================*/



//==========================================================
// CHART SYNCHRONIZATION
//==========================================================

function updateChart(){

    const actualLabels=[];

    dashboard.actualData.forEach((_,index)=>{

        actualLabels.push(
            (index+1).toString()
        );

    });

    const predictionLabels=[];

    dashboard.predictedData.forEach((_,index)=>{

        predictionLabels.push(
            "P"+(index+1)
        );

    });

    aqiChart.data.labels=[

        ...actualLabels,

        ...predictionLabels

    ];

    const predictionPadding=

    new Array(
        dashboard.actualData.length
    ).fill(null);

    aqiChart.data.datasets[0].data=[

        ...dashboard.actualData

    ];

    aqiChart.data.datasets[1].data=[

        ...predictionPadding,

        ...dashboard.predictedData

    ];

    aqiChart.update();

}



//==========================================================
// FORECAST GENERATION
//==========================================================

function refreshPrediction(){

    generatePrediction();

    updateChart();

    updateSummary();

}



//==========================================================
// FORECAST BUTTONS
//==========================================================

function activateForecastButton(button){

    forecastButtons.forEach(btn=>{

        btn.classList.remove("active");

    });

    button.classList.add("active");

}



function setupForecastButtons(){

    forecastButtons.forEach(button=>{

        button.addEventListener(

            "click",

            function(){

                const minutes=

                Number(

                    this.dataset.time ||

                    this.textContent.replace(/\D/g,"")

                );

                dashboard.forecastMinutes=

                minutes;

                activateForecastButton(this);

                refreshPrediction();

                addActivity(

                    "Forecast changed to "

                    +minutes+

                    " minutes."

                );

            }

        );

    });

}



//==========================================================
// AQI SLIDER
//==========================================================

function updateSliderDisplay(){

    if(sliderValue){

        sliderValue.textContent=

        slider.value;

    }

    if(forecastValue){

        forecastValue.textContent=

        slider.value;

    }

}



function setupSlider(){

    if(!slider) return;

    slider.value=

    dashboard.currentAQI;

    updateSliderDisplay();

    slider.addEventListener(

        "input",

        ()=>{

            updateSliderDisplay();

        }

    );

}



//==========================================================
// APPLY AQI CHANGE
//==========================================================

function applyAQI(value){

    dashboard.previousAQI=

    dashboard.currentAQI;

    dashboard.currentAQI=

    clamp(

        Number(value),

        0,

        500

    );

    dashboard.actualData.push(

        dashboard.currentAQI

    );

    if(

        dashboard.actualData.length>24

    ){

        dashboard.actualData.shift();

    }

    dashboard.todayData=[

        ...dashboard.actualData

    ];

    refreshPrediction();

    synchronizeDashboard();

}



//==========================================================
// SIMULATION BUTTON
//==========================================================

function setupSimulation(){

    if(!simulateBtn) return;

    simulateBtn.addEventListener(

        "click",

        ()=>{

            applyAQI(

                slider.value

            );

            addActivity(

                "AQI manually simulated to "

                +dashboard.currentAQI+"."

            );

        }

    );

}