import fitdecode
import pandas as pd
from pathlib import Path
from datetime import datetime
import re
from fitdecode.reader import ErrorHandling
import numpy as np

# ---------- CONFIG ----------
# En GitHub Actions el repo queda en el directorio de trabajo,
# así que FIT/ y data/ son rutas relativas al raíz del repo.
CARPETA_FIT = Path("FIT")
DATA_DIR    = Path("data")

CSV_FULL_RUN        = DATA_DIR / "running_60d_full.csv"
CSV_SUMMARY_RUN     = DATA_DIR / "running_60d_summary.csv"
TXT_COMPARACION_RUN = DATA_DIR / "running_comparacion.txt"

CSV_FULL_CYC        = DATA_DIR / "cycling_60d_full.csv"
CSV_SUMMARY_CYC     = DATA_DIR / "cycling_60d_summary.csv"
TXT_COMPARACION_CYC = DATA_DIR / "cycling_comparacion.txt"

VENTANA_DIAS     = 60
DEPORTES_VALIDOS = {"running", "cycling"}

# ---------- FECHA ----------
def obtener_fecha(nombre):
    m = re.search(r'(\d{4})\.(\d{2})\.(\d{2})\s+(\d{2})\.(\d{2})', nombre)
    return datetime(*map(int, m.groups())) if m else None

# ---------- PROCESAR FIT ----------
def procesar_fit(file_path, activity_id):
    rows  = []
    sport = None
    fecha = obtener_fecha(file_path.stem)

    try:
        with fitdecode.FitReader(str(file_path), error_handling=ErrorHandling.IGNORE) as fit:
            for frame in fit:
                if not isinstance(frame, fitdecode.records.FitDataMessage):
                    continue

                if frame.name == "session":
                    sport = frame.get_value("sport")

                elif frame.name == "record":
                    row = {}
                    for f in frame.fields:
                        try:
                            row[f.name] = f.value
                        except Exception:
                            row[f.name] = None

                    row["activity_id"]   = activity_id
                    row["activity_date"] = fecha

                    hr  = row.get("heart_rate")
                    spd = row.get("enhanced_speed")

                    row["meters_per_beat"] = (
                        (spd * 60) / hr
                        if hr and spd and hr > 0
                        else np.nan
                    )

                    rows.append(row)

    except Exception as e:
        print(f"  Error en {file_path.name}: {e}")

    return sport, rows

# ---------- MÉTRICAS ----------
def calcular_summary(df, sport="running"):
    df = df.copy()
    df["heart_rate"]     = pd.to_numeric(df.get("heart_rate"),     errors="coerce")
    df["enhanced_speed"] = pd.to_numeric(df.get("enhanced_speed"), errors="coerce")
    df["distance"]       = pd.to_numeric(df.get("distance"),       errors="coerce")
    df = df.dropna(subset=["heart_rate", "enhanced_speed"])

    if df.empty:
        return None

    hr_med     = df["heart_rate"].mean()
    speed_med  = df["enhanced_speed"].mean()
    m_per_beat = df["meters_per_beat"].mean()
    eficiencia = (df["enhanced_speed"] / df["heart_rate"]).mean()
    vvo2       = df.nlargest(10, "enhanced_speed")["enhanced_speed"].mean() * 3.6

    if sport == "running":
        pace     = 1000 / (speed_med * 60) if speed_med > 0 else np.nan
        pace_key = "ritmo_medio"
    else:
        pace     = speed_med * 3.6
        pace_key = "velocidad_kmh"

    df_160 = df[(df["heart_rate"] > 140) & (df["heart_rate"] < 180)]
    if not df_160.empty:
        coef      = np.polyfit(df_160["heart_rate"], df_160["enhanced_speed"], 1)
        speed_160 = np.polyval(coef, 160)
        pace_160  = (
            1000 / (speed_160 * 60)
            if sport == "running"
            else speed_160 * 3.6
        )
    else:
        pace_160 = np.nan

    pace_160_key = "ritmo_160ppm" if sport == "running" else "velocidad_160ppm_kmh"

    mitad  = len(df) // 2
    first  = df.iloc[:mitad]
    second = df.iloc[mitad:]
    ef1    = (first["enhanced_speed"]  / first["heart_rate"]).mean()
    ef2    = (second["enhanced_speed"] / second["heart_rate"]).mean()
    desacople = ((ef2 - ef1) / ef1) * 100 if ef1 else np.nan

    return {
        "fecha":         df["activity_date"].iloc[0],
        "hr_media":      hr_med,
        pace_key:        pace,
        pace_160_key:    pace_160,
        "metros_latido": m_per_beat,
        "eficiencia":    eficiencia,
        "vvo2max":       vvo2,
        "desacople_%":   desacople,
    }

# ---------- INTERPRETACIÓN ----------
def interpretar_metrica(nombre, cambio):
    if np.isnan(cambio):
        return ""
    if "ritmo" in nombre or "desacople" in nombre:
        return "MEJORA" if cambio < 0 else "EMPEORA"
    else:
        return "MEJORA" if cambio > 0 else "EMPEORA"

# ---------- COMPARACIÓN ----------
def comparar_avanzado(df_summary):
    n          = len(df_summary)
    mitad      = n // 2
    recientes  = df_summary.head(mitad)
    anteriores = df_summary.iloc[mitad:]
    total      = df_summary

    lineas = ["=" * 90, "COMPARACION AVANZADA\n"]

    for col in df_summary.columns:
        if col == "fecha":
            continue

        old        = anteriores[col].mean()
        new        = recientes[col].mean()
        total_mean = total[col].mean()

        change = ((new - old) / old) * 100 if old and not np.isnan(old) else np.nan
        interp = interpretar_metrica(col, change)

        lineas.append(
            f"{col:20} | "
            f"{old:8.3f} -> {new:8.3f} | "
            f"{change:7.2f}% | "
            f"vs_total: {new - total_mean:+.3f} | "
            f"{interp}"
        )

    lineas.append("=" * 90)
    return "\n".join(lineas)

# ---------- GUARDAR DEPORTE ----------
def guardar_deporte(all_rows, summary_rows, csv_full, csv_summary, txt_comp, etiqueta):
    if not all_rows:
        print(f"\nNo hay datos de {etiqueta}.")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    df_full = pd.DataFrame(all_rows)
    df_full.to_csv(csv_full, index=False, encoding="utf-8-sig")
    print(f"\n  {csv_full}  ({len(df_full)} registros)")

    df_summary = pd.DataFrame(summary_rows).sort_values("fecha", ascending=False)
    df_summary.to_csv(csv_summary, index=False, encoding="utf-8-sig")
    print(f"  {csv_summary}  ({len(df_summary)} actividades)")

    texto = comparar_avanzado(df_summary)
    print(f"\n{etiqueta.upper()} -- COMPARACION\n{texto}")

    with open(txt_comp, "w", encoding="utf-8") as f:
        f.write(texto)
    print(f"  {txt_comp}")

# ---------- MAIN ----------
def main():
    if not CARPETA_FIT.exists():
        print(f"Carpeta FIT no encontrada: {CARPETA_FIT.resolve()}")
        return

    hoy    = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    limite = hoy - pd.Timedelta(days=VENTANA_DIAS)

    all_files = sorted(
        CARPETA_FIT.glob("*.fit"),
        key=lambda x: obtener_fecha(x.stem) or datetime.min,
        reverse=True,
    )

    files = [
        f for f in all_files
        if (fecha_f := obtener_fecha(f.stem)) and limite <= fecha_f <= hoy
    ]

    print(f"\nVentana: {limite.date()} -> {hoy.date()}  ({VENTANA_DIAS} dias)")
    print(f"Ficheros en ventana: {len(files)} de {len(all_files)} totales\n")

    run_rows, run_summary = [], []
    cyc_rows, cyc_summary = [], []
    run_count = cyc_count = 0
    activity_id = 0

    for f in files:
        print(f"-> {f.name}")
        sport, rows = procesar_fit(f, activity_id)
        sport_str   = str(sport).lower()

        if not rows:
            print("   Sin registros")
            continue

        print(f"   Registros: {len(rows)} | Sport: {sport}")

        if not any(k in sport_str for k in DEPORTES_VALIDOS):
            print("   X  Ignorado (no es running ni cycling)")
            continue

        if "run" in sport_str:
            print("   OK RUNNING")
            df_act  = pd.DataFrame(rows)
            metrics = calcular_summary(df_act, sport="running")
            if metrics:
                run_summary.append(metrics)
            run_rows.extend(rows)
            run_count  += 1
            activity_id += 1

        elif "cycl" in sport_str:
            print("   OK CYCLING")
            df_act  = pd.DataFrame(rows)
            metrics = calcular_summary(df_act, sport="cycling")
            if metrics:
                cyc_summary.append(metrics)
            cyc_rows.extend(rows)
            cyc_count  += 1
            activity_id += 1

    print(f"\n{'='*50}")
    print(f"Running : {run_count} actividades | {len(run_rows)} registros")
    print(f"Cycling : {cyc_count} actividades | {len(cyc_rows)} registros")
    print(f"{'='*50}")

    guardar_deporte(run_rows, run_summary,
                    CSV_FULL_RUN, CSV_SUMMARY_RUN, TXT_COMPARACION_RUN, "running")
    guardar_deporte(cyc_rows, cyc_summary,
                    CSV_FULL_CYC, CSV_SUMMARY_CYC, TXT_COMPARACION_CYC, "cycling")

if __name__ == "__main__":
    main()
