const ctx = document.getElementById('aqiChart');

new Chart(ctx, {
    type: 'line',
    data: {
        labels: [
            '10:00',
            '10:10',
            '10:20',
            'Now',
            '+15 min',
            '+30 min'
        ],
        datasets: [
            {
                label: 'Actual AQI',
                data: [140, 150, 165, 185, null, null],
                borderColor: 'blue',
                backgroundColor: 'blue',
                tension: 0.4
            },
            {
                label: 'Predicted AQI',
                data: [null, null, null, 185, 205, 225],
                borderColor: 'red',
                backgroundColor: 'red',
                borderDash: [5,5],
                tension: 0.4
            }
        ]
    },
    options: {
        responsive: true,
        plugins: {
            legend: {
                position: 'top'
            }
        },
        scales: {
            y: {
                beginAtZero: false
            }
        }
    }
});