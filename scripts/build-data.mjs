import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const XLSX = require("xlsx");

const ROOT = process.cwd();
const INPUT_DIR = path.join(ROOT, "input");
const OUTPUT_DIR = path.join(ROOT, "data");
const OUTPUT_FILE = path.join(OUTPUT_DIR, "dashboard-data.json");

const SUPPORTED_EXTENSIONS = new Set([".xlsx", ".xls"]);

const MONTHS = {
  JAN: 0,
  FEB: 1,
  MAR: 2,
  APR: 3,
  MAY: 4,
  JUN: 5,
  JUL: 6,
  AUG: 7,
  SEP: 8,
  OCT: 9,
  NOV: 10,
  DEC: 11,
  ENE: 0,
  ABR: 3,
  AGO: 7,
  DIC: 11
};

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

  const tempRows = [];

  for (const file of files) {
    const filePath = path.join(INPUT_DIR, file);

    const workbook = XLSX.readFile(filePath, {
      cellDates: true,
      raw: true
    });

    for (const sheetName of workbook.SheetNames) {
      const sheet = workbook.Sheets[sheetName];

      const rows = XLSX.utils.sheet_to_json(sheet, {
        defval: "",
        raw: true
      });

      for (const row of rows) {
        const normalized = normalizeRow(row, file, sheetName);

        if (normalized) {
          tempRows.push(normalized);
        }
      }
    }
  }

  const workerFleet = buildWorkerFleetMap(tempRows);
  const workerRank = buildWorkerRankMap(tempRows);

  const records = tempRows
    .map((row) => {
      const fleet = row.fleet || workerFleet.get(row.worker_id) || "";
      const rank_code = row.rank_code || workerRank.get(row.worker_id) || "";
      const rank_label = normalizeRankLabel(rank_code);

      if (!fleet) return null;

      return {
        date: row.date,
        worker_id: row.worker_id,
        worker_name: row.worker_name,
        aircraft_type_desc: row.aircraft_type_desc,
        fleet,
        rank_code,
        rank_label,
        source: row.source,
        hours: row.hours,
        source_file: row.source_file,
        source_sheet: row.source_sheet
      };
    })
    .filter(Boolean)
    .filter((row) => row.source === "publicado" || row.source === "efectuado");

  const payload = {
    generated_at: new Date().toISOString(),
    record_count: records.length,
    records
  };

  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(payload, null, 2), "utf8");

  console.log(`OK: ${records.length} registros escritos en ${OUTPUT_FILE}`);
}

function normalizeRow(row, file, sheetName) {
  const workerId = cleanText(
    pick(row, [
      "crew_id",
      "Crew ID",
      "Staff Num",
      "staff_num",
      "worker_id",
      "employee_id",
      "rut",
      "RUT",
      "codigo",
      "Código",
      "CODIGO",
      "legajo"
    ])
  );

  if (!workerId) return null;

  const firstName = cleanText(pick(row, ["First Name", "first_name", "firstname"]));
  const lastName = cleanText(pick(row, ["Last Name", "last_name", "lastname"]));

  const workerName =
    cleanText(
      pick(row, [
        "nombre_completo",
        "worker_name",
        "name",
        "Nombre",
        "TRABAJADOR",
        "Trabajador",
        "tripulante",
        "Tripulante",
        "crew_name"
      ])
    ) ||
    cleanText(`${lastName} ${firstName}`) ||
    workerId;

  const dateValue = pick(row, [
    "str_dt",
    "Str Dt",
    "Str Date",
    "date",
    "fecha",
    "Fecha",
    "FECHA",
    "flight_date",
    "duty_date",
    "DIA",
    "Día",
    "dia"
  ]);

  const date = normalizeDate(dateValue);

  if (!date) return null;

  const aircraft =
    cleanText(
      pick(row, [
        "aircraft_type_desc",
        "AIRCRAFT_TYPE_DESC",
        "Aircraft Type Desc",
        "Fleet",
        "fleet",
        "aircraftType",
        "aircraft_type",
        "Aircraft Type",
        "tipo_avion",
        "Tipo Avion"
      ])
    ) || "";

  const rankRaw = pick(row, [
    "rank_code",
    "Rank Code",
    "RANK_CODE",
    "rank",
    "Rank",
    "cargo",
    "Cargo"
  ]);

  const fleet = inferFleet(aircraft);
  const rank_code = normalizeRankCode(rankRaw);
  const rank_label = normalizeRankLabel(rankRaw);

  const blockTime = pick(row, [
    "block_time",
    "Block Time",
    "BLH",
    "blh",
    "hours",
    "Horas",
    "horas",
    "HRS",
    "hrs",
    "total_hours"
  ]);

  const hours = normalizeHours(blockTime);

  const source = inferSourceFromRow(row) || inferSourceFromFilename(file);

  return {
    date,
    worker_id: normalizeWorkerId(workerId),
    worker_name: workerName,
    aircraft_type_desc: aircraft,
    fleet,
    rank_code,
    rank_label,
    source,
    hours,
    source_file: file,
    source_sheet: sheetName
  };
}

function buildWorkerFleetMap(rows) {
  const map = new Map();

  for (const row of rows) {
    if (row.worker_id && row.fleet && !map.has(row.worker_id)) {
      map.set(row.worker_id, row.fleet);
    }
  }

  return map;
}

function buildWorkerRankMap(rows) {
  const map = new Map();

  for (const row of rows) {
    if (row.worker_id && row.rank_code && !map.has(row.worker_id)) {
      map.set(row.worker_id, row.rank_code);
    }
  }

  return map;
}

function pick(row, aliases) {
  for (const alias of aliases) {
    if (Object.prototype.hasOwnProperty.call(row, alias)) {
      const value = row[alias];
      if (value !== null && value !== undefined && String(value).trim() !== "") {
        return value;
      }
    }
  }

  const lookup = new Map();

  for (const [key, value] of Object.entries(row)) {
    lookup.set(normalizeHeader(key), value);
  }

  for (const alias of aliases) {
    const value = lookup.get(normalizeHeader(alias));

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

function cleanText(value) {
  return String(value ?? "").trim();
}

function normalizeWorkerId(value) {
  const text = cleanText(value);

  if (/^\d+(\.0)?$/.test(text)) {
    return String(Number(text));
  }

  return text.replace(/^0+/, "") || text;
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

  const text = String(value).trim().toUpperCase();

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

  const ddMmmYyyy = text.match(/^(\d{1,2})([A-ZÁÉÍÓÚÑ]{3})(\d{4})$/);

  if (ddMmmYyyy) {
    const day = Number(ddMmmYyyy[1]);
    const monthText = ddMmmYyyy[2]
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "");
    const year = Number(ddMmmYyyy[3]);

    if (MONTHS[monthText] !== undefined) {
      return toIsoDate(new Date(year, MONTHS[monthText], day));
    }
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

function normalizeHours(value) {
  if (value === null || value === undefined || value === "") return 0;

  if (value instanceof Date && !isNaN(value)) {
    return round2(value.getHours() + value.getMinutes() / 60 + value.getSeconds() / 3600);
  }

  if (typeof value === "number") {
    if (!Number.isFinite(value)) return 0;

    if (value > 0 && value <= 1) {
      return round2(value * 24);
    }

    return round2(value);
  }

  const text = String(value).trim();

  if (!text) return 0;

  const time = text.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);

  if (time) {
    const hours = Number(time[1]);
    const minutes = Number(time[2]);
    const seconds = Number(time[3] || 0);

    return round2(hours + minutes / 60 + seconds / 3600);
  }

  const number = Number(
    text
      .replace(/\./g, "")
      .replace(",", ".")
      .replace(/[^\d.-]/g, "")
  );

  if (!Number.isFinite(number)) return 0;

  if (number > 0 && number <= 1) {
    return round2(number * 24);
  }

  return round2(number);
}

function inferFleet(value) {
  const text = cleanText(value).toUpperCase();

  if (!text) return "";

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

function normalizeRankCode(value) {
  const text = cleanText(value).toUpperCase();

  if (text === "CP" || text.includes("CAP")) return "CP";
  if (text === "FO" || text.includes("PRI")) return "FO";

  return "";
}

function normalizeRankLabel(value) {
  const code = normalizeRankCode(value);

  if (code === "CP") return "Capitán";
  if (code === "FO") return "Primer Oficial";

  return "";
}

function inferSourceFromRow(row) {
  const value = cleanText(
    pick(row, [
      "tipo_rol",
      "Tipo Rol",
      "source",
      "Source",
      "origen",
      "Origen"
    ])
  ).toLowerCase();

  if (value.includes("ejecut") || value.includes("efect")) return "efectuado";
  if (value.includes("pub")) return "publicado";

  return "";
}

function inferSourceFromFilename(file) {
  const text = file.toLowerCase();

  if (text.includes("publicado") || text.includes("pub")) return "publicado";
  if (text.includes("efectuado") || text.includes("efect")) return "efectuado";

  return "";
}

function round2(value) {
  return Math.round((Number(value || 0) + Number.EPSILON) * 100) / 100;
}

function ensureDirectory(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}
