import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import * as XLSX from "xlsx";

const ROOT = process.cwd();
const INPUT_DIR = path.join(ROOT, "input");
const OUTPUT_DIR = path.join(ROOT, "data");
const OUTPUT_FILE = path.join(OUTPUT_DIR, "dashboard-data.json");

const SUPPORTED_EXTENSIONS = new Set([".xlsx", ".xls"]);

const DATE_KEYS = [
  "date",
  "fecha",
  "Fecha",
  "FECHA",
  "flight_date",
  "duty_date",
  "DIA",
  "Día",
  "dia"
];

const HOURS_KEYS = [
  "hours",
  "Horas",
  "horas",
  "HRS",
  "hrs",
  "block_hours",
  "total_hours",
  "BLH",
  "blh"
];

const WORKER_ID_KEYS = [
  "worker_id",
  "trabajador_id",
  "employee_id",
  "rut",
  "RUT",
  "codigo",
  "Código",
  "CODIGO",
  "crew_id",
  "legajo"
];

const WORKER_NAME_KEYS = [
  "worker_name",
  "name",
  "nombre",
  "Nombre",
  "TRABAJADOR",
  "Trabajador",
  "tripulante",
  "Tripulante",
  "crew_name"
];

const AIRCRAFT_KEYS = [
  "aircraft_type_desc",
  "AIRCRAFT_TYPE_DESC",
  "Aircraft Type Desc",
  "aircraftType",
  "aircraft_type",
  "tipo_avion",
  "Tipo Avion"
];

main();

function main() {
  ensureDirectory(OUTPUT_DIR);

  if (!fs.existsSync(INPUT_DIR)) {
    throw new Error(`No existe la carpeta ${INPUT_DIR}`);
  }

  const files = fs
    .readdirSync(INPUT_DIR)
    .filter((file) => SUPPORTED_EXTENSIONS.has(path.extname(file).toLowerCase()))
    .sort();

  const records = [];

  for (const file of files) {
    const filePath = path.join(INPUT_DIR, file);
    const source = inferSourceFromFilename(file);

    const workbook = XLSX.readFile(filePath, {
      cellDates: true,
      raw: false
    });

    for (const sheetName of workbook.SheetNames) {
      const sheet = workbook.Sheets[sheetName];

      const rows = XLSX.utils.sheet_to_json(sheet, {
        defval: "",
        raw: false
      });

      for (const row of rows) {
        const normalized = normalizeRow(row, {
          file,
          sheetName,
          source
        });

        if (normalized) {
          records.push(normalized);
        }
      }
    }
  }

  const payload = {
    generated_at: new Date().toISOString(),
    record_count: records.length,
    records
  };

  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(payload, null, 2), "utf8");

  console.log(`OK: ${records.length} registros escritos en ${OUTPUT_FILE}`);
}

function normalizeRow(row, meta) {
  const dateValue = pick(row, DATE_KEYS);
  const hoursValue = pick(row, HOURS_KEYS);
  const aircraftValue = pick(row, AIRCRAFT_KEYS);

  const date = normalizeDate(dateValue);
  const hours = normalizeNumber(hoursValue);
  const aircraft_type_desc = String(aircraftValue || "").trim();

  if (!date) return null;
  if (!Number.isFinite(hours)) return null;
  if (!aircraft_type_desc) return null;

  const fleet = inferFleet(aircraft_type_desc);

  if (!fleet) return null;

  const workerId =
    pick(row, WORKER_ID_KEYS) ||
    pick(row, WORKER_NAME_KEYS) ||
    "SIN_ID";

  const workerName =
    pick(row, WORKER_NAME_KEYS) ||
    pick(row, WORKER_ID_KEYS) ||
    "Sin nombre";

  return {
    date,
    worker_id: String(workerId).trim(),
    worker_name: String(workerName).trim(),
    aircraft_type_desc,
    fleet,
    source: meta.source,
    hours,
    source_file: meta.file,
    source_sheet: meta.sheetName
  };
}

function pick(row, keys) {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(row, key)) {
      const value = row[key];
      if (value !== null && value !== undefined && String(value).trim() !== "") {
        return value;
      }
    }
  }

  const normalizedLookup = new Map();

  for (const [key, value] of Object.entries(row)) {
    normalizedLookup.set(normalizeHeader(key), value);
  }

  for (const key of keys) {
    const value = normalizedLookup.get(normalizeHeader(key));

    if (value !== null && value !== undefined && String(value || "").trim() !== "") {
      return value;
    }
  }

  return "";
}

function normalizeHeader(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function normalizeDate(value) {
  if (!value) return "";

  if (value instanceof Date && !isNaN(value)) {
    return toIsoDate(value);
  }

  if (typeof value === "number") {
    const excelEpoch = new Date(Date.UTC(1899, 11, 30));
    return toIsoDate(new Date(excelEpoch.getTime() + value * 86400000));
  }

  const text = String(value).trim();

  if (!text) return "";

  if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
    return text.slice(0, 10);
  }

  const dmy = text.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$/);
  if (dmy) {
    const day = Number(dmy[1]);
    const month = Number(dmy[2]) - 1;
    let year = Number(dmy[3]);

    if (year < 100) year += 2000;

    return toIsoDate(new Date(year, month, day));
  }

  const parsed = new Date(text);

  if (!isNaN(parsed)) {
    return toIsoDate(parsed);
  }

  return "";
}

function toIsoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function normalizeNumber(value) {
  if (typeof value === "number") return value;

  if (value === null || value === undefined || value === "") return 0;

  const text = String(value)
    .replace(/\./g, "")
    .replace(",", ".")
    .replace(/[^\d.-]/g, "");

  const number = Number(text);

  return Number.isFinite(number) ? number : 0;
}

function inferFleet(value) {
  const text = String(value || "").toUpperCase().trim();

  if (text.includes("787")) return "Wide Body";

  if (
    text.includes("32X") ||
    text.includes("320") ||
    text.includes("321") ||
    text.includes("319") ||
    /^32[A-Z0-9]/.test(text)
  ) {
    return "Narrow Body";
  }

  return "";
}

function inferSourceFromFilename(file) {
  const text = file.toLowerCase();

  if (text.includes("pub")) return "publicado";
  if (text.includes("efect")) return "efectuado";

  return "desconocido";
}

function ensureDirectory(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}
