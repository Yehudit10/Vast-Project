# analyze_sensors.py  — robust version (no stuck/gap rules, improved safety)

from pathlib import Path
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from scipy.stats import zscore
from profiles_runtime import export_profiles

# ---------------- Config ----------------
# Default to the uploaded dataset location; can be overridden by env var.
DATA_PATH = Path(os.getenv("DATA_PATH", "/mnt/data/plant_health_data.csv"))
OUT_DIR = Path("reports")
PLOTS_DIR = OUT_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

SENSORS = ["Soil_Moisture", "Ambient_Temperature", "Humidity"]
VALID_RANGES = {
    "Soil_Moisture": (0, 100),
    "Humidity": (0, 100),
    "Ambient_Temperature": (-30, 60),
}

EPS_STD = 1e-6 

# -------------- Helpers -----------------
def _as_numeric(df: pd.DataFrame, col: str) -> pd.Series:
    s = pd.to_numeric(df[col], errors="coerce")
    return s


def read_and_clean(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    df = pd.read_csv(path)

    if "Timestamp" not in df.columns:
        raise ValueError("CSV must contain a 'Timestamp' column")
    
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df = df.dropna(subset=["Timestamp"])
    
    if "Plant_ID" not in df.columns:
        df["Plant_ID"] = 1

    for c, (lo, hi) in VALID_RANGES.items():
        if c in df.columns:
            df[c] = _as_numeric(df, c)
            df.loc[(df[c] < lo) | (df[c] > hi), c] = np.nan

    df = df.sort_values(["Plant_ID", "Timestamp"]).reset_index(drop=True)
    return df


def _safe_std_by(grouped: pd.core.groupby.SeriesGroupBy) -> pd.Series:
    std = grouped.std()
    if std.notna().any():
        m = std.mean(skipna=True)
        std = std.fillna(m if pd.notna(m) else 0.0)
    else:
        std = std.fillna(0.0)
    std = std.clip(lower=EPS_STD)
    return std

# --------- Baselines ---------
def baseline_daily(d: pd.DataFrame, col: str) -> pd.DataFrame:
    x = d[["Timestamp", col]].copy()
    x["hod"] = x["Timestamp"].dt.hour
    prof = x.groupby("hod")[col].median().reindex(range(24)).interpolate(limit_direction="both")
    std = _safe_std_by(x.groupby("hod")[col]).reindex(range(24)).fillna(method="ffill").fillna(method="bfill")
    out = x.copy()
    out["baseline"] = out["hod"].map(prof)
    out["band_std"] = out["hod"].map(std)
    out["lower"] = out["baseline"] - 2 * out["band_std"]
    out["upper"] = out["baseline"] + 2 * out["band_std"]
    out = out.drop(columns=["hod"])
    out["bl_type"] = "daily"
    return out

def baseline_weekly(d: pd.DataFrame, col: str) -> pd.DataFrame:
    x = d[["Timestamp", col]].copy()
    x["dow"] = x["Timestamp"].dt.dayofweek  # 0..6
    x["hod"] = x["Timestamp"].dt.hour       # 0..23
    prof = x.groupby(["dow","hod"])[col].median().unstack()
    prof = prof.reindex(index=range(7), columns=range(24))
    prof = prof.interpolate(axis=0, limit_direction="both").interpolate(axis=1, limit_direction="both")
    std = _safe_std_by(x.groupby(["dow","hod"])[col]).unstack()
    std = std.reindex(index=range(7), columns=range(24))
    std = std.fillna(method="ffill").fillna(method="bfill").fillna(EPS_STD)

    out = x.copy()
  
    dow_idx = out["dow"].to_numpy(dtype=int)
    hod_idx = out["hod"].to_numpy(dtype=int)
    prof_np = prof.to_numpy()
    std_np  = std.to_numpy()
    out["baseline"] = prof_np[dow_idx, hod_idx]
    out["band_std"] = std_np[dow_idx, hod_idx]
    out["lower"] = out["baseline"] - 2 * out["band_std"]
    out["upper"] = out["baseline"] + 2 * out["band_std"]
    out = out.drop(columns=["dow","hod"])
    out["bl_type"] = "weekly"
    return out

def baseline_seasonal(d: pd.DataFrame, col: str) -> pd.DataFrame:
    x = d[["Timestamp", col]].copy()
    x["doy"] = x["Timestamp"].dt.dayofyear  # 1..366
    x["hod"] = x["Timestamp"].dt.hour       # 0..23
    doy_prof = x.groupby("doy")[col].median().reindex(range(1, 367)).interpolate(limit_direction="both")
    hod_prof = x.groupby("hod")[col].median().reindex(range(24)).interpolate(limit_direction="both")
    std_hod = (
    _safe_std_by(x.groupby("hod")[col])
    .reindex(range(24))
    .ffill()
    .bfill()
    ).clip(lower=EPS_STD)
    out = x.copy()
    out["baseline"] = 0.5 * out["doy"].map(doy_prof) + 0.5 * out["hod"].map(hod_prof)
    out["band_std"] = out["hod"].map(std_hod)
    out["lower"] = out["baseline"] - 2 * out["band_std"]
    out["upper"] = out["baseline"] + 2 * out["band_std"]
    out = out.drop(columns=["doy","hod"])
    out["bl_type"] = "seasonal"
    return out

# ---------------- Forecasts ----------------
def short_forecast(series: pd.Series):
    s = series.dropna()
    if len(s) < 48:
        return None
    try:
        if isinstance(s.index, pd.DatetimeIndex):
            s = s.asfreq("H")
        else:
            s.index = pd.date_range(start=pd.Timestamp.now().floor("H") - pd.Timedelta(hours=len(s)-1),
                                    periods=len(s), freq="H")
    except Exception:
        pass

    sp = 168 if len(s) >= 336 else 24
    try:
        model = ExponentialSmoothing(
            s, trend="add", seasonal="add", seasonal_periods=sp, initialization_method="estimated"
        ).fit()
        return model.forecast(sp)
    except Exception:
        return None


# ---------------- Anomalies ----------------
def detect_flags(dfb: pd.DataFrame, col: str) -> pd.DataFrame:
    y = dfb.copy()
 
    valid = y[col].notna()
    y["residual"] = np.where(valid, y[col] - y["baseline"], np.nan)

    y["flag_band"] = np.where(valid, (y[col] < y["lower"]) | (y[col] > y["upper"]), False)

    diff = y[col].diff()
    z = zscore(diff.fillna(0.0).to_numpy(), nan_policy="omit")
    y["diff"] = diff
    y["flag_spike"] = False
    if z is not None and len(z) == len(y):
        y["flag_spike"] = np.abs(pd.Series(z, index=y.index).fillna(0.0)) > 3.0

    ma = y["residual"].abs().rolling(24, min_periods=12).mean()

    band_std = y["band_std"].fillna(EPS_STD).clip(lower=EPS_STD)
    y["flag_break"] = (ma > (1.5 * band_std)).fillna(False)

    y["is_anomaly"] = y[["flag_band","flag_spike","flag_break"]].any(axis=1)
    return y

# ---------------- Plotting ----------------
def plot_one(dfp: pd.DataFrame, col: str, plant, label: str):
   
    if dfp[col].notna().sum() == 0:
        return
    
    low = dfp["lower"].fillna(dfp["baseline"])
    up  = dfp["upper"].fillna(dfp["baseline"])

    plt.figure(figsize=(12, 5))
    plt.plot(dfp["Timestamp"], dfp[col], label=col)
    plt.plot(dfp["Timestamp"], dfp["baseline"], label=f"baseline ({label})", linewidth=2)
    plt.fill_between(dfp["Timestamp"], low, up, alpha=0.2, label="band")
    anom = dfp[dfp["is_anomaly"] & dfp[col].notna()]
    if not anom.empty:
        plt.scatter(anom["Timestamp"], anom[col], marker="x", s=36, label="anomaly")
    plt.title(f"Plant {plant} — {col} — {label}")
    plt.xlabel("Time"); plt.ylabel(col)
    plt.legend(); plt.tight_layout()
    out = PLOTS_DIR / f"plant{plant}_{col}_{label}.png"
    plt.savefig(out); plt.close()

# ---------------- Main ----------------
def main():
    print(f"Reading data from: {DATA_PATH}")
    df = read_and_clean(DATA_PATH)
    export_profiles(df)
    plants = df["Plant_ID"].dropna().unique().tolist()
    if not plants:
        print(" No Plant_ID values found.")
        return
    print(f"Found {len(plants)} plants/sensors: {plants[:10]}{'...' if len(plants)>10 else ''}")
    out_rows = []

    if os.getenv("EXPORT_PROFILES", "0") == "1":
        try:
           
            export_profiles(df)
            print(" Exported runtime profiles to reports/models/")
        except Exception as e:
            print(f" Failed to export profiles: {e}")

    for plant in plants:
        d0 = df[df["Plant_ID"] == plant].copy()
        for col in SENSORS:
            if col not in d0.columns:
                continue
            d0[col] = _as_numeric(d0, col)
            d = d0[["Timestamp", col]].dropna().copy()
            if d.empty:
                continue

            bl_daily  = baseline_daily(d, col)
            bl_weekly = baseline_weekly(d, col) if len(d) >= 24*7 else None
            bl_season = baseline_seasonal(d, col) if d["Timestamp"].dt.year.nunique() >= 2 or len(d) >= 24*60 else None

            _ = short_forecast(d[col]) 

            for bl, name in ((bl_daily, "daily"), (bl_weekly, "weekly"), (bl_season, "seasonal")):
                if bl is None:
                    continue
                det = detect_flags(bl, col)
                det["Plant_ID"] = plant
                det["Sensor"] = col
                det["BaselineType"] = name
                out_rows.append(det)
                try:
                    plot_one(det, col, plant, name)
                except Exception as e:
                    print(f" plot error Plant={plant} Sensor={col} Type={name}: {e}")

    if out_rows:
        out = pd.concat(out_rows, ignore_index=True)
        keep = ["Timestamp","Plant_ID","Sensor","BaselineType"] + \
               [c for c in SENSORS if c in out.columns] + \
               ["baseline","lower","upper","residual","flag_band","flag_spike","flag_break","is_anomaly"]
        out = out[keep].sort_values(["Plant_ID","Sensor","BaselineType","Timestamp"])
        OUT_DIR.mkdir(exist_ok=True, parents=True)
        out_csv = OUT_DIR / "anomalies_report.csv"
        out.to_csv(out_csv, index=False)
     
        n_anom = int(out["is_anomaly"].sum())
        print(f"Anomalies report: {out_csv}  (total anomalies: {n_anom})")
        print(f" Plots saved in: {PLOTS_DIR}")
    else:
        print(" No results — maybe no suitable columns/data.")

if __name__ == "__main__":
    main()
