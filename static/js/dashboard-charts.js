(function () {
    const CHART_PANEL_ID = "attendance-chart-panel";
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

    function resolveColor(variable, fallback) {
        try {
            const probe = document.createElement("span");
            probe.style.cssText = "position:absolute;visibility:hidden;color:var(" + variable + ")";
            document.documentElement.appendChild(probe);
            const color = getComputedStyle(probe).color;
            probe.remove();
            return color && color !== "rgba(0, 0, 0, 0)" ? color : fallback;
        } catch (_) {
            return fallback;
        }
    }

    function themeColors() {
        const isDark = document.documentElement.getAttribute("data-theme") === "dark";
        return {
            text: resolveColor("--text", isDark ? "#C3C1BA" : "#3A2F33"),
            grid: resolveColor("--border", isDark ? "#3E3E38" : "#E8E0E3"),
            surface: resolveColor("--bg-elevated", isDark ? "#1B1B1B" : "#FFFBFC"),
        };
    }

    function initAttendanceChart() {
        const panel = getPanel();
        if (!panel || typeof Chart === "undefined") {
            return;
        }
        const colors = themeColors();
        const attendanceColors = [
            resolveColor("--chart-present", "#166534"),
            resolveColor("--chart-absent", "#991b1b"),
            resolveColor("--chart-late", "#92400e"),
            resolveColor("--chart-leave", "#1e40af"),
            resolveColor("--chart-incomplete", "#9a3412"),
            resolveColor("--chart-missing", "#6b7280"),
        ];
        if (typeof Chart !== "undefined" && Chart.defaults) {
            Chart.defaults.color = colors.text;
            Chart.defaults.borderColor = colors.grid;
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
                        backgroundColor: attendanceColors,
                        borderColor: colors.surface,
                        borderWidth: 2,
                    },
                ],
            },
            options: {
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            color: colors.text,
                        },
                    },
                },
            },
        });
    }

    function isChartPanel(target) {
        return target && target.id === CHART_PANEL_ID;
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAttendanceChart);
    } else {
        initAttendanceChart();
    }

    document.body.addEventListener("htmx:beforeSwap", function (event) {
        if (isChartPanel(event.detail.target) || (event.detail.target && event.detail.target.id === "spa-view")) {
            destroyAttendanceChart();
        }
    });

    document.body.addEventListener("htmx:afterSwap", function (event) {
        if (isChartPanel(event.detail.target) || document.getElementById("attendance-chart")) {
            initAttendanceChart();
        }
    });

    window.addEventListener("themechange", function () {
        initAttendanceChart();
    });
})();
