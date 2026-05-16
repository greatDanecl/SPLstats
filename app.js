const DATA_URL = "./data/dashboard-data.json";
const DAN_MAX_ANUAL = 1000;

let rawData = [];
let charts = {
  publishedVsEffected: null,
  workerHours: null,
  adherence: null
};

const els = {
  fleetFilter: document.getElementById("fleetFilter"),
  monthFilter: document.getElementById("monthFilter"),
  workerFilter: document.getElementById("workerFilter"),
  clearFilters: document.getElementById("clearFilters"),
  emptyState: document.getElementById("emptyState"),
  dashboardContent: document.getElementById("dashboardContent"),
  kpiGrid: document.getElementById("kpiGrid"),
  detailTableBody: document.getElementById("detailTableBody")
};

init();

async function init() {
  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });

    if (!response.ok) {
      throw new Error(`No se pudo cargar ${DATA_URL}`);
    }

    const payload = await response.json();

    rawData = normalizeRecords(payload.records || payload || []);

    populateFleetFilter();
    bindEvents();
    render();
  } catch (error) {
    console.error(error);
    els.emptyState.innerHTML = `
      <div class="empty-icon">⚠️</div>
      <h2>No se pudo cargar la información</h2>
      <p>Verifique que exista el archivo <strong>data/dashboard-data.json</strong>.</p>
    `;
  }
}

function normalizeRecords(records) {
  return records
    .map((record) => {
      const date = parseDate(record.date || record.fecha || record.Fecha);

      const aircraftType =
        record.aircraft_type_desc ||
        record.AIRCRAFT_TYPE_DESC ||
        record.aircraftType ||
        "";

      return {
        date,
        month: date ? toMonthKey(date) : "",
        year: date ? date.getFullYear() : null,
        worker_id: String(
          record.worker_id ||
          record.trabajador_id ||
          record.employee_id ||
          record.rut ||
          record.RUT ||
          record.codigo ||
          record.Codigo ||
          record.name ||
          record.trabajador ||
          "SIN_ID"
        ).trim(),
        worker_name: String(
          record.worker_name ||
          record.name ||
          record.trabajador ||
          record.Trabajador ||
          record.nombre ||
          record.Nombre ||
          "Sin nombre"
        ).trim(),
        aircraft_type_desc: String(aircraftType).trim(),
        fleet: inferFleet(aircraftType),
        source: normalizeSource(record.source || record.tipo || record.Tipo || record.origen || ""),
        hours: toNumber(
          record.hours ||
          record.horas ||
          record.Horas ||
          record.block_hours ||
          record.total_hours ||
          0
        )
      };
    })
    .filter((record) => {
      return (
        record.date instanceof Date &&
        !isNaN(record.date) &&
        record.fleet &&
        record.source &&
        Number.isFinite(record.hours)
      );
    });
}

function parseDate(value) {
  if (value instanceof Date) return value;

  if (typeof value === "number") {
    const excelEpoch = new Date(Date.UTC(1899, 11, 30));
    return new Date(excelEpoch.getTime() + value * 86400000);
  }

  if (!value) return null;

  const text = String(value).trim();

  if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
    return new Date(`${text.slice(0, 10)}T00:00:00`);
  }

  const dmy = text.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$/);
  if (dmy) {
    const day = Number(dmy[1]);
    const month = Number(dmy[2]) - 1;
    let year = Number(dmy[3]);
    if (year < 100) year += 2000;
    return new Date(year, month, day);
  }

  const parsed = new Date(text);
  return parsed;
}

function toMonthKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function inferFleet(value) {
  const text = String(value || "").toUpperCase().trim();

  if (!text) return "";

  if (text.includes("787")) return "Wide Body";

  if (/32[A-Z0-9]/.test(text) || text.includes("32X") || text.includes("320") || text.includes("321") || text.includes("319")) {
    return "Narrow Body";
  }

  return "";
}

function normalizeSource(value) {
  const text = String(value || "").toLowerCase();

  if (text.includes("pub")) return "publicado";
  if (text.includes("efect")) return "efectuado";

  return "";
}

function toNumber(value) {
  if (typeof value === "number") return value;

  if (value === null || value === undefined || value === "") return 0;

  const cleaned = String(value)
    .replace(/\./g, "")
    .replace(",", ".")
    .replace(/[^\d.-]/g, "");

  const number = Number(cleaned);
  return Number.isFinite(number) ? number : 0;
}

function populateFleetFilter() {
  const fleets = [...new Set(rawData.map((d) => d.fleet).filter(Boolean))].sort();

  els.fleetFilter.innerHTML = `
    <option value="">Seleccione flota</option>
    ${fleets.map((fleet) => `<option value="${escapeHtml(fleet)}">${escapeHtml(fleet)}</option>`).join("")}
  `;
}

function populateMonthFilter(records) {
  const months = [...new Set(records.map((d) => d.month).filter(Boolean))].sort();

  els.monthFilter.innerHTML = `
    <option value="">Todos los meses</option>
    ${months.map((month) => `<option value="${month}">${formatMonth(month)}</option>`).join("")}
  `;

  els.monthFilter.disabled = !els.fleetFilter.value;
}

function populateWorkerFilter(records) {
  const workers = getWorkers(records);

  els.workerFilter.innerHTML = `
    <option value="">Todos los trabajadores</option>
    ${workers
      .map((worker) => `<option value="${escapeHtml(worker.worker_id)}">${escapeHtml(worker.worker_name)}</option>`)
      .join("")}
  `;

  els.workerFilter.disabled = !els.fleetFilter.value;
}

function bindEvents() {
  els.fleetFilter.addEventListener("change", () => {
    els.monthFilter.value = "";
    els.workerFilter.value = "";

    const fleetRecords = rawData.filter((d) => d.fleet === els.fleetFilter.value);
    populateMonthFilter(fleetRecords);
    populateWorkerFilter(fleetRecords);

    render();
  });

  els.monthFilter.addEventListener("change", render);
  els.workerFilter.addEventListener("change", render);

  els.clearFilters.addEventListener("click", () => {
    els.fleetFilter.value = "";
    els.monthFilter.innerHTML = `<option value="">Todos los meses</option>`;
    els.workerFilter.innerHTML = `<option value="">Todos los trabajadores</option>`;
    els.monthFilter.disabled = true;
    els.workerFilter.disabled = true;
    render();
  });
}

function render() {
  const fleet = els.fleetFilter.value;

  if (!fleet) {
    els.emptyState.classList.remove("hidden");
    els.dashboardContent.classList.add("hidden");
    destroyCharts();
    return;
  }

  els.emptyState.classList.add("hidden");
  els.dashboardContent.classList.remove("hidden");

  const month = els.monthFilter.value;
  const workerId = els.workerFilter.value;

  const fleetRecordsAllMonths = rawData.filter((d) => d.fleet === fleet);

  let filteredRecords = fleetRecordsAllMonths;

  if (month) {
    filteredRecords = filteredRecords.filter((d) => d.month === month);
  }

  if (workerId) {
    filteredRecords = filteredRecords.filter((d) => d.worker_id === workerId);
  }

  renderKpis(filteredRecords, fleetRecordsAllMonths, workerId);
  renderCharts(filteredRecords, fleetRecordsAllMonths, workerId);
  renderTable(filteredRecords, fleetRecordsAllMonths);
}

function renderKpis(filteredRecords, fleetRecordsAllMonths, workerId) {
  const publishedHours = sumHours(filteredRecords, "publicado");
  const effectedHours = sumHours(filteredRecords, "efectuado");
  const difference = effectedHours - publishedHours;
  const adherence = publishedHours > 0 ? effectedHours / publishedHours : null;

  const selectedYear = getSelectedCalendarYear(fleetRecordsAllMonths);
  const ytdHours = getYtdHours(workerId, selectedYear, fleetRecordsAllMonths);
  const remainingDanHours = Math.max(0, DAN_MAX_ANUAL - ytdHours);

  const workerCount = getWorkers(filteredRecords).length;

  els.kpiGrid.innerHTML = `
    ${kpiCard("👥", "Trabajadores", formatInteger(workerCount))}
    ${kpiCard("📘", "Horas publicadas", formatHours(publishedHours))}
    ${kpiCard("✅", "Horas efectuadas", formatHours(effectedHours))}
    ${kpiCard("↔️", "Diferencia", formatSignedHours(difference))}
    ${kpiCard("📊", `Horas YTD ${selectedYear}`, formatHours(ytdHours), "Solo año calendario")}
    ${kpiCard("🛡️", "Saldo DAN", formatHours(remainingDanHours), "Máximo anual 1000 h")}
  `;
}

function kpiCard(icon, label, value, sub = "") {
  return `
    <article class="kpi-card">
      <div class="kpi-icon">${icon}</div>
      <div class="kpi-content">
        <div class="kpi-label">${escapeHtml(label)}</div>
        <div class="kpi-value">${escapeHtml(value)}</div>
        ${sub ? `<div class="kpi-sub">${escapeHtml(sub)}</div>` : ""}
      </div>
    </article>
  `;
}

function renderCharts(filteredRecords, fleetRecordsAllMonths, workerId) {
  const lineRecords = workerId
    ? fleetRecordsAllMonths.filter((d) => d.worker_id === workerId)
    : fleetRecordsAllMonths;

  renderPublishedVsEffectedChart(lineRecords);
  renderWorkerHoursChart(filteredRecords);
  renderAdherenceChart(filteredRecords);
}

function renderPublishedVsEffectedChart(records) {
  const monthlyData = buildMonthlyPublishedVsEffected(records);

  const ctx = document.getElementById("publishedVsEffectedChart");

  if (charts.publishedVsEffected) charts.publishedVsEffected.destroy();

  charts.publishedVsEffected = new Chart(ctx, {
    type: "line",
    data: {
      labels: monthlyData.map((d) => formatMonth(d.month)),
      datasets: [
        {
          label: "Publicado",
          data: monthlyData.map((d) => round1(d.publicado)),
          tension: 0.25,
          borderWidth: 3,
          pointRadius: 5,
          pointHoverRadius: 7
        },
        {
          label: "Efectuado",
          data: monthlyData.map((d) => round1(d.efectuado)),
          tension: 0.25,
          borderWidth: 3,
          pointRadius: 5,
          pointHoverRadius: 7
        }
      ]
    },
    options: defaultChartOptions("Horas")
  });
}

function buildMonthlyPublishedVsEffected(records) {
  const monthly = {};

  records.forEach((d) => {
    if (!d.month) return;

    if (!monthly[d.month]) {
      monthly[d.month] = {
        month: d.month,
        publicado: 0,
        efectuado: 0
      };
    }

    if (d.source === "publicado") {
      monthly[d.month].publicado += Number(d.hours || 0);
    }

    if (d.source === "efectuado") {
      monthly[d.month].efectuado += Number(d.hours || 0);
    }
  });

  return Object.values(monthly).sort((a, b) => a.month.localeCompare(b.month));
}

function renderWorkerHoursChart(records) {
  const summary = summarizeByWorker(records)
    .sort((a, b) => b.efectuado - a.efectuado)
    .slice(0, 15);

  const ctx = document.getElementById("workerHoursChart");

  if (charts.workerHours) charts.workerHours.destroy();

  charts.workerHours = new Chart(ctx, {
    type: "bar",
    data: {
      labels: summary.map((d) => d.worker_name),
      datasets: [
        {
          label: "Horas efectuadas",
          data: summary.map((d) => round1(d.efectuado)),
          borderWidth: 1
        }
      ]
    },
    options: defaultChartOptions("Horas")
  });
}

function renderAdherenceChart(records) {
  const summary = summarizeByWorker(records)
    .filter((d) => d.publicado > 0)
    .map((d) => ({
      ...d,
      adherence: d.efectuado / d.publicado
    }))
    .sort((a, b) => b.adherence - a.adherence)
    .slice(0, 15);

  const ctx = document.getElementById("adherenceChart");

  if (charts.adherence) charts.adherence.destroy();

  charts.adherence = new Chart(ctx, {
    type: "bar",
    data: {
      labels: summary.map((d) => d.worker_name),
      datasets: [
        {
          label: "Adherencia",
          data: summary.map((d) => round1(d.adherence * 100)),
          borderWidth: 1
        }
      ]
    },
    options: defaultChartOptions("%")
  });
}

function defaultChartOptions(unit) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: {
          usePointStyle: true,
          boxWidth: 8
        }
      },
      tooltip: {
        callbacks: {
          label(context) {
            const value = context.parsed.y;
            return `${context.dataset.label}: ${value}${unit === "%" ? "%" : " h"}`;
          }
        }
      }
    },
    scales: {
      x: {
        ticks: {
          maxRotation: 45,
          minRotation: 0
        },
        grid: {
          display: false
        }
      },
      y: {
        beginAtZero: true,
        ticks: {
          callback(value) {
            return unit === "%" ? `${value}%` : `${value} h`;
          }
        }
      }
    }
  };
}

function renderTable(filteredRecords, fleetRecordsAllMonths) {
  const selectedYear = getSelectedCalendarYear(fleetRecordsAllMonths);
  const summary = summarizeByWorker(filteredRecords).sort((a, b) =>
    a.worker_name.localeCompare(b.worker_name)
  );

  els.detailTableBody.innerHTML = summary
    .map((row) => {
      const diff = row.efectuado - row.publicado;
      const adherence = row.publicado > 0 ? row.efectuado / row.publicado : null;
      const ytd = getYtdHours(row.worker_id, selectedYear, fleetRecordsAllMonths);
      const saldo = Math.max(0, DAN_MAX_ANUAL - ytd);

      return `
        <tr>
          <td>${escapeHtml(row.worker_name)}</td>
          <td><span class="badge">${escapeHtml(row.fleet)}</span></td>
          <td class="numeric">${formatHours(row.publicado)}</td>
          <td class="numeric">${formatHours(row.efectuado)}</td>
          <td class="numeric">${formatSignedHours(diff)}</td>
          <td class="numeric">${adherence === null ? "—" : formatPercent(adherence)}</td>
          <td class="numeric">${formatHours(ytd)}</td>
          <td class="numeric">${formatHours(saldo)}</td>
        </tr>
      `;
    })
    .join("");
}

function summarizeByWorker(records) {
  const map = new Map();

  records.forEach((d) => {
    const key = d.worker_id;

    if (!map.has(key)) {
      map.set(key, {
        worker_id: d.worker_id,
        worker_name: d.worker_name,
        fleet: d.fleet,
        publicado: 0,
        efectuado: 0
      });
    }

    const row = map.get(key);

    if (d.source === "publicado") row.publicado += d.hours;
    if (d.source === "efectuado") row.efectuado += d.hours;
  });

  return [...map.values()];
}

function getWorkers(records) {
  const map = new Map();

  records.forEach((d) => {
    if (!map.has(d.worker_id)) {
      map.set(d.worker_id, {
        worker_id: d.worker_id,
        worker_name: d.worker_name
      });
    }
  });

  return [...map.values()].sort((a, b) => a.worker_name.localeCompare(b.worker_name));
}

function getSelectedCalendarYear(records) {
  const selectedMonth = els.monthFilter.value;

  if (selectedMonth) {
    return Number(selectedMonth.slice(0, 4));
  }

  const years = records.map((d) => d.year).filter(Boolean);

  if (!years.length) {
    return new Date().getFullYear();
  }

  return Math.max(...years);
}

function getYtdHours(workerId, year, baseRecords) {
  return baseRecords
    .filter((d) => {
      if (d.source !== "efectuado") return false;
      if (d.year !== year) return false;
      if (workerId && d.worker_id !== workerId) return false;
      return true;
    })
    .reduce((sum, d) => sum + d.hours, 0);
}

function sumHours(records, source) {
  return records
    .filter((d) => d.source === source)
    .reduce((sum, d) => sum + d.hours, 0);
}

function destroyCharts() {
  Object.keys(charts).forEach((key) => {
    if (charts[key]) {
      charts[key].destroy();
      charts[key] = null;
    }
  });
}

function formatHours(value) {
  return `${round1(value).toLocaleString("es-CL")} h`;
}

function formatSignedHours(value) {
  const rounded = round1(value);
  const sign = rounded > 0 ? "+" : "";
  return `${sign}${rounded.toLocaleString("es-CL")} h`;
}

function formatInteger(value) {
  return Number(value || 0).toLocaleString("es-CL");
}

function formatPercent(value) {
  return `${round1(value * 100).toLocaleString("es-CL")}%`;
}

function formatMonth(monthKey) {
  if (!monthKey) return "—";

  const [year, month] = monthKey.split("-").map(Number);
  const date = new Date(year, month - 1, 1);

  return new Intl.DateTimeFormat("es-CL", {
    month: "short",
    year: "numeric"
  }).format(date);
}

function round1(value) {
  return Math.round((Number(value || 0) + Number.EPSILON) * 10) / 10;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
