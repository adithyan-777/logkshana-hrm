(function () {
    const CHART_PANEL_ID = "attendance-chart-panel";
    const CHART_COLORS = [
        "#166534",
        "#991b1b",
        "#92400e",
        "#1e40af",
        "#9a3412",
        "#6b7280",
    ];

    let attendanceChart = null;

    function getPanel() {
        return document.getElementById(CHART_PANEL_ID);
    }

    function destroyAttendanceChart() {
        if (attendanceChart) {
            attendanceChart.destroy();
            attendanceChart = null;
        }
    }

    function initAttendanceChart() {
        const panel = getPanel();
        if (!panel || typeof Chart === "undefined") {
            return;
        }

        const dataElement = panel.querySelector("#attendance-chart-data");
        const canvas = panel.querySelector("#attendance-chart");
        const emptyState = panel.querySelector("#attendance-chart-empty");

        if (!dataElement || !canvas) {
            return;
        }

        const chartData = JSON.parse(dataElement.textContent);
        const hasData = chartData.values.some(function (value) {
            return value > 0;
        });

        destroyAttendanceChart();

        if (!hasData) {
            canvas.hidden = true;
            if (emptyState) {
                emptyState.hidden = false;
            }
            return;
        }

        canvas.hidden = false;
        if (emptyState) {
            emptyState.hidden = true;
        }

        attendanceChart = new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: chartData.labels,
                datasets: [
                    {
                        data: chartData.values,
                        backgroundColor: CHART_COLORS,
                        borderWidth: 0,
                    },
                ],
            },
            options: {
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                    },
                },
            },
        });
    }

    function isChartPanel(target) {
        return target && target.id === CHART_PANEL_ID;
    }

    document.addEventListener("DOMContentLoaded", initAttendanceChart);

    document.body.addEventListener("htmx:beforeSwap", function (event) {
        if (isChartPanel(event.detail.target)) {
            destroyAttendanceChart();
        }
    });

    document.body.addEventListener("htmx:afterSwap", function (event) {
        if (isChartPanel(event.detail.target) || document.getElementById("attendance-chart")) {
            initAttendanceChart();
        }
    });
})();
