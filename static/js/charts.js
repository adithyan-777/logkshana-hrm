(function () {
  /** Resolve a CSS variable to a concrete color Chart.js can paint. */
  function resolveColor(varName, fallback) {
    const probe = document.createElement("span");
    probe.style.cssText = "position:absolute;left:-9999px;top:0;pointer-events:none;color:var(" + varName + ")";
    document.body.appendChild(probe);
    const color = getComputedStyle(probe).color;
    probe.remove();
    if (!color || color === "rgba(0, 0, 0, 0)" || color === "transparent") return fallback;
    return color;
  }

  function chartColors() {
    return {
      accent: resolveColor("--accent", "#e6987e"),
      text: resolveColor("--text-muted", "#85837D"),
      textStrong: resolveColor("--text", "#3E3E38"),
      grid: resolveColor("--border", "#ebebeb"),
      bg: resolveColor("--bg-elevated", "#FAF9F1"),
      popover: resolveColor("--bg-popover", "#FAF9F1"),
      border: resolveColor("--border", "#ebebeb"),
      success: resolveColor("--success", "#16a34a"),
      warning: resolveColor("--warning", "#ca8a04"),
      danger: resolveColor("--danger", "#dc2626"),
      info: resolveColor("--info", "#2563eb"),
      muted: resolveColor("--text-dim", "#85837D"),
      warm: resolveColor("--accent-warm", "#e6987e"),
    };
  }

  let attendanceChart = null;
  let revenueChart = null;
  let statusChart = null;

  function tooltipOptions(colors) {
    return {
      backgroundColor: colors.popover,
      borderColor: colors.border,
      borderWidth: 1,
      titleColor: colors.textStrong,
      bodyColor: colors.text,
      displayColors: true,
    };
  }

  function applyChartDefaults(colors) {
    Chart.defaults.color = colors.text;
    Chart.defaults.borderColor = colors.grid;
    Chart.defaults.font.family = '"Geist Variable", "Geist", system-ui, sans-serif';
  }

  function initCharts() {
    const el = document.getElementById("chart-data");
    if (!el || typeof Chart === "undefined") return;

    const data = JSON.parse(el.textContent);
    const colors = chartColors();
    applyChartDefaults(colors);

    const attendanceCtx = document.getElementById("attendanceChart");
    if (attendanceCtx && data.attendance) {
      attendanceChart?.destroy();
      attendanceChart = new Chart(attendanceCtx, {
        type: "doughnut",
        data: {
          labels: data.attendance.labels,
          datasets: [{
            data: data.attendance.values,
            backgroundColor: [
              colors.success,
              colors.danger,
              colors.warning,
              colors.info,
              colors.muted,
              withAlpha(colors.danger, 0.65),
            ],
            borderColor: colors.bg,
            borderWidth: 2,
            hoverBorderColor: colors.bg,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: "62%",
          plugins: {
            legend: {
              position: "bottom",
              labels: {
                color: colors.text,
                boxWidth: 12,
                padding: 12,
                usePointStyle: true,
                pointStyle: "circle",
              },
            },
            tooltip: tooltipOptions(colors),
          },
        },
      });
    }

    const revenueCtx = document.getElementById("revenueChart");
    if (revenueCtx && data.revenue) {
      revenueChart?.destroy();
      revenueChart = new Chart(revenueCtx, {
        type: "line",
        data: {
          labels: data.revenue.labels,
          datasets: [{
            label: "Attendance",
            data: data.revenue.values,
            borderColor: colors.accent,
            backgroundColor: withAlpha(colors.accent, 0.15),
            fill: true,
            tension: 0.35,
            pointRadius: 3,
            pointBackgroundColor: colors.accent,
            pointBorderColor: colors.bg,
            pointBorderWidth: 2,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            title: { display: false },
            tooltip: tooltipOptions(colors),
          },
          scales: {
            y: {
              beginAtZero: true,
              grid: { color: withAlpha(colors.grid, 0.7), drawBorder: false },
              border: { display: false },
              ticks: { color: colors.text },
            },
            x: {
              grid: { display: false },
              border: { display: false },
              ticks: { color: colors.text },
            },
          },
        },
      });
    }

    const statusCtx = document.getElementById("statusChart");
    if (statusCtx && data.status) {
      statusChart?.destroy();
      statusChart = new Chart(statusCtx, {
        type: "doughnut",
        data: {
          labels: data.status.labels,
          datasets: [{
            data: data.status.values,
            backgroundColor: [colors.warning, colors.success, colors.info, colors.danger],
            borderColor: colors.bg,
            borderWidth: 2,
            hoverBorderColor: colors.bg,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: "58%",
          plugins: {
            legend: {
              position: "bottom",
              labels: {
                color: colors.text,
                usePointStyle: true,
                pointStyle: "circle",
              },
            },
            tooltip: tooltipOptions(colors),
          },
        },
      });
    }
  }

  function withAlpha(color, alpha) {
    if (!color) return `rgba(230,152,126,${alpha})`;
    const m = String(color).match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/i);
    if (m) return `rgba(${m[1]}, ${m[2]}, ${m[3]}, ${alpha})`;
    if (color[0] === "#" && color.length >= 7) {
      const r = parseInt(color.slice(1, 3), 16);
      const g = parseInt(color.slice(3, 5), 16);
      const b = parseInt(color.slice(5, 7), 16);
      return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }
    return color;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCharts);
  } else {
    initCharts();
  }

  document.body.addEventListener("htmx:afterSwap", function (evt) {
    if (evt.target && evt.target.id === "attendance-chart-panel") {
      initCharts();
    }
  });
})();
