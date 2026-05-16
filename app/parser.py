from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime, time
import pandas as pd
import numpy as np

MONTHS = {
    "JAN":"01", "ENE":"01", "FEB":"02", "MAR":"03", "APR":"04", "ABR":"04", "MAY":"05",
    "JUN":"06", "JUL":"07", "AUG":"08", "AGO":"08", "SEP":"09", "OCT":"10", "NOV":"11", "DEC":"12", "DIC":"12",
}
ABSENCE_LONG = {"VAC", "SICK", "OOF"}


def clean_text(value):
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    if s == "" or s.lower() in {"nan", "nat", "none"}:
        return None
    return s


def parse_sabre_date(value):
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value)
    s = str(value).strip().upper()
    m = re.match(r"^(\d{1,2})([A-ZÁÉÍÓÚÑ]{3})(\d{4})$", s)
    if m:
        month = MONTHS.get(m.group(2))
        if month:
            return pd.Timestamp(f"{m.group(3)}-{month}-{int(m.group(1)):02d}")
    return pd.to_datetime(value, errors="coerce")


def time_to_hours(value) -> float:
    if pd.isna(value) or value is None:
        return 0.0
    if isinstance(value, datetime):
        value = value.time()
    if isinstance(value, time):
        return value.hour + value.minute / 60 + value.second / 3600
    if isinstance(value, (int, float, np.number)):
        # Excel time fraction
        if 0 <= float(value) <= 1:
            return float(value) * 24
        return float(value)
    s = str(value).strip()
    if not s or s.lower() in {"nan", "nat"}:
        return 0.0
    parts = s.split(":")
    try:
        if len(parts) >= 2:
            return int(parts[0]) + int(parts[1]) / 60 + (int(parts[2]) / 3600 if len(parts) >= 3 else 0)
        return float(s)
    except Exception:
        return 0.0


def read_excel_flexible(path: Path) -> pd.DataFrame:
    # Try likely header rows. Some files have a blank/header preamble.
    for header in [0, 1, 2, 3, 4, 5]:
        try:
            df = pd.read_excel(path, header=header)
        except Exception:
            continue
        df.columns = [str(c).strip() for c in df.columns]
        cols = set(df.columns)
        if {"crew_id", "activity_code"}.issubset(cols) or {"Staff Num", "Activity"}.issubset(cols) or "Sabre Code" in cols:
            return df
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def infer_tipo_from_filename(path: Path) -> str:
    name = path.stem.upper()
    if "EFECT" in name or "EJEC" in name:
        return "Ejecutado"
    if "PUB" in name:
        return "Publicado"
    return "No informado"


def normalize_fleet_value(value):
    s = clean_text(value)
    if not s:
        return None
    s = s.upper().replace(" ", "")
    if "787" in s:
        return "787"
    if re.search(r"^32[A-Z0-9]$", s) or s.startswith("32"):
        return "32X"
    return None


def operation_from_fleet(fleet):
    f = clean_text(fleet)
    if f == "787":
        return "Wide Body"
    if f == "32X":
        return "Narrow Body"
    return "Sin clasificar"


def get_col(df: pd.DataFrame, name: str, default=None):
    if name in df.columns:
        return df[name]
    return pd.Series([default] * len(df), index=df.index)


def normalize_roster(path: Path) -> pd.DataFrame:
    df = read_excel_flexible(path)
    if "Sabre Code" in df.columns:
        return pd.DataFrame()

    if "crew_id" in df.columns:
        out = pd.DataFrame({
            "crew_id": get_col(df, "crew_id").astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(8),
            "nombre_completo": get_col(df, "nombre_completo"),
            "company_code": get_col(df, "company_code"),
            "fleet_raw": get_col(df, "aircraft_type_desc"),
            "rank_code": get_col(df, "rank_code"),
            "str_dt": pd.to_datetime(get_col(df, "str_dt"), errors="coerce"),
            "str_tm": get_col(df, "str_tm"),
            "end_dt": pd.to_datetime(get_col(df, "end_dt"), errors="coerce"),
            "end_tm": get_col(df, "end_tm"),
            "activity_code": get_col(df, "activity_code"),
            "departure_airport_code": get_col(df, "departure_airport_code"),
            "arrival_airport_code": get_col(df, "arrival_airport_code"),
            "block_time": get_col(df, "block_time"),
            "periodo": get_col(df, "periodo").astype(str),
            "tipo_rol": get_col(df, "tipo_rol").astype(str),
        })
    else:
        first = get_col(df, "First Name", "").fillna("").astype(str)
        last = get_col(df, "Last Name", "").fillna("").astype(str)
        out = pd.DataFrame({
            "crew_id": get_col(df, "Staff Num").astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(8),
            "nombre_completo": (last + " " + first).str.strip(),
            "company_code": get_col(df, "Company"),
            "fleet_raw": get_col(df, "Fleet"),
            "rank_code": get_col(df, "Rank"),
            "str_dt": get_col(df, "Str Dt").map(parse_sabre_date),
            "str_tm": get_col(df, "Str Tm"),
            "end_dt": get_col(df, "End Dt").map(parse_sabre_date),
            "end_tm": get_col(df, "End Tm"),
            "activity_code": get_col(df, "Activity"),
            "departure_airport_code": get_col(df, "Dep Port"),
            "arrival_airport_code": get_col(df, "Arv Port"),
            "block_time": get_col(df, "Block Time"),
        })
        periods = out["str_dt"].dt.to_period("M").astype(str)
        mode = periods[periods != "NaT"].mode()
        out["periodo"] = mode.iloc[0] if len(mode) else None
        out["tipo_rol"] = infer_tipo_from_filename(path)

    out["activity_code"] = out["activity_code"].astype(str).str.strip().str.upper()
    out["rank_code"] = out["rank_code"].astype(str).str.strip().str.upper()
    out["tipo_rol"] = out["tipo_rol"].astype(str).str.strip().str.title()
    out.loc[out["tipo_rol"].str.contains("Efect|Ejec", case=False, na=False), "tipo_rol"] = "Ejecutado"
    out.loc[out["tipo_rol"].str.contains("Pub", case=False, na=False), "tipo_rol"] = "Publicado"
    out["fleet"] = out["fleet_raw"].map(normalize_fleet_value)
    out["block_hours"] = out["block_time"].map(time_to_hours)
    out["source_file"] = path.name
    out = out.dropna(subset=["crew_id", "rank_code", "activity_code", "periodo"])
    out = out[out["crew_id"].ne("00000nan")]
    return out


def load_code_dictionary(raw_dir: Path) -> pd.DataFrame:
    candidates = list(raw_dir.glob("*DIGOS*.xlsx")) + list(raw_dir.glob("*CODIGOS*.xlsx")) + list(raw_dir.glob("*CÓDIGOS*.xlsx"))
    if not candidates:
        return pd.DataFrame(columns=["activity_code", "description", "activity_type", "code_ifn"])
    df = read_excel_flexible(candidates[0])
    df.columns = [str(c).strip() for c in df.columns]
    rename = {"Sabre Code": "activity_code", "Description": "description", "Activity type": "activity_type", "Code IFN": "code_ifn"}
    df = df.rename(columns=rename)
    keep = [c for c in ["activity_code", "description", "activity_type", "code_ifn"] if c in df.columns]
    if "activity_code" not in keep:
        return pd.DataFrame(columns=["activity_code", "description", "activity_type", "code_ifn"])
    out = df[keep].copy()
    for col in ["description", "activity_type", "code_ifn"]:
        if col not in out.columns:
            out[col] = None
    out["activity_code"] = out["activity_code"].astype(str).str.strip().str.upper()
    return out.dropna(subset=["activity_code"]).drop_duplicates("activity_code")


def classify_activity(df: pd.DataFrame, codes: pd.DataFrame) -> pd.DataFrame:
    out = df.merge(codes, on="activity_code", how="left")
    code = out["activity_code"].fillna("")
    is_flight = code.str.match(r"^LA\d+", na=False)
    out.loc[is_flight, ["description", "activity_type", "code_ifn"]] = ["Vuelo", "Flight", "FLT"]

    prefix_rules = [
        (code.str.startswith("AS", na=False), "Turno en aeropuerto", "Airport Stand by", "AS"),
        (code.str.startswith("HS", na=False), "Turno en domicilio", "Home Stand by", "HS"),
    ]
    for mask, desc, typ, ifn in prefix_rules:
        fill = mask & out["description"].isna()
        out.loc[fill, ["description", "activity_type", "code_ifn"]] = [desc, typ, ifn]

    manual = {
        "B": ("Día blanco", "Blank", "B"), "VAC": ("Vacaciones", "Absence", "VAC"), "DO": ("Día libre", "DayOff", "DO"),
        "SICK": ("Licencia médica", "Absence", "SICK"), "VUSA": ("Ausencia visado", "Absence", "VUSA"), "Q": ("Bloque libre quincena", "DayOff", "Q"),
        "OOF": ("Fuera de vuelo", "Absence", "OOF"), "DR": ("Día libre solicitado", "DayOff", "DR"), "RL": ("REVA", "Ground", "RL"),
        "CLA": ("Clases en tierra", "Ground training", "CLA"),
    }
    for k, (desc, typ, ifn) in manual.items():
        mask = (code == k) & out["description"].isna()
        out.loc[mask, ["description", "activity_type", "code_ifn"]] = [desc, typ, ifn]

    out["description"] = out["description"].fillna("No clasificado")
    out["activity_type"] = out["activity_type"].fillna("Other")
    out["code_ifn"] = out["code_ifn"].fillna(out["activity_code"])
    out["is_flight"] = is_flight
    out["is_long_absence"] = out["code_ifn"].isin(ABSENCE_LONG) | out["activity_code"].isin(ABSENCE_LONG)
    out["is_productive"] = out["is_flight"] | out["activity_type"].str.contains("Stand by|Ground|training|SIM|Airport|Home", case=False, na=False)
    return out


def propagate_operation_by_worker(df: pd.DataFrame) -> pd.DataFrame:
    """Asigna habilitación/operación al piloto completo usando la moda de flota en filas de vuelo con dato."""
    out = df.copy()
    flight_fleet = out[out["is_flight"] & out["fleet"].notna()].copy()
    mode_by_worker = {}
    conflict_by_worker = {}
    for crew_id, g in flight_fleet.groupby("crew_id"):
        counts = g["fleet"].value_counts(dropna=True)
        if len(counts):
            mode_by_worker[crew_id] = counts.index[0]
            conflict_by_worker[crew_id] = len(counts) > 1
    out["fleet_inferred"] = out["crew_id"].map(mode_by_worker)
    out["operation_type"] = out["fleet_inferred"].map(operation_from_fleet).fillna("Sin clasificar")
    out["fleet_conflict"] = out["crew_id"].map(lambda x: bool(conflict_by_worker.get(x, False)))
    return out


def load_all(raw_dir: str | Path = "data/raw") -> pd.DataFrame:
    raw_dir = Path(raw_dir)
    rosters = []
    for file in sorted(raw_dir.glob("*.xlsx")):
        up = file.name.upper()
        if "~$" in file.name or "DIGOS" in up or "CODIG" in up or "CÓDIG" in up:
            continue
        df = normalize_roster(file)
        if len(df):
            rosters.append(df)
    if not rosters:
        return pd.DataFrame()
    data = pd.concat(rosters, ignore_index=True)
    codes = load_code_dictionary(raw_dir)
    data = classify_activity(data, codes)
    data = propagate_operation_by_worker(data)
    # Stable types for JSON/CSV
    for c in ["crew_id", "nombre_completo", "company_code", "rank_code", "activity_code", "periodo", "tipo_rol", "source_file", "description", "activity_type", "code_ifn", "fleet", "fleet_inferred", "operation_type"]:
        if c in data.columns:
            data[c] = data[c].astype("string")
    return data


def worker_month_metrics(df: pd.DataFrame) -> pd.DataFrame:
    gcols = ["periodo", "operation_type", "tipo_rol", "rank_code", "crew_id", "nombre_completo"]
    return df.groupby(gcols, dropna=False).agg(
        block_hours=("block_hours", "sum"),
        flight_events=("is_flight", "sum"),
        long_absence_days=("is_long_absence", "sum"),
        duty_items=("activity_code", "count"),
        distinct_activity_types=("activity_type", "nunique"),
    ).reset_index()


def adherence_by_worker(df: pd.DataFrame) -> pd.DataFrame:
    m = worker_month_metrics(df)
    idx = ["periodo", "operation_type", "rank_code", "crew_id", "nombre_completo"]
    piv = m.pivot_table(index=idx, columns="tipo_rol", values="block_hours", aggfunc="sum", fill_value=0).reset_index()
    for col in ["Publicado", "Ejecutado"]:
        if col not in piv.columns:
            piv[col] = 0.0
    base = piv["Publicado"].replace(0, np.nan)
    piv["adherencia_horas"] = (1 - (piv["Ejecutado"] - piv["Publicado"]).abs() / base).clip(lower=0, upper=1)
    piv.loc[(piv["Publicado"].eq(0)) & (piv["Ejecutado"].eq(0)), "adherencia_horas"] = 1
    piv.loc[(piv["Publicado"].eq(0)) & (piv["Ejecutado"].gt(0)), "adherencia_horas"] = 0
    piv["delta_horas"] = piv["Ejecutado"] - piv["Publicado"]
    return piv


def eligible_for_peer_average(df: pd.DataFrame, max_long_absence_days: int = 7) -> pd.DataFrame:
    met = worker_month_metrics(df)
    absdays = met.groupby(["periodo", "operation_type", "rank_code", "crew_id"], dropna=False)["long_absence_days"].max().reset_index()
    absdays["eligible_peer_avg"] = absdays["long_absence_days"] <= max_long_absence_days
    return absdays
