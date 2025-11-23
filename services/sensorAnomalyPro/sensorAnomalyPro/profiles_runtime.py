from pathlib import Path
from typing import Dict, Optional
import numpy as np
import pandas as pd
BASE_DIR = Path(__file__).resolve().parent  
MODELS_DIR = BASE_DIR / "reports" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

SENSORS = ["Soil_Moisture", "Ambient_Temperature", "Humidity"]

# ---------- Helpers ----------
def _safe_interp(series: pd.Series, full_index):
    s = series.reindex(full_index)
    return s.interpolate(limit_direction="both")

# ---------- Export (train) ----------
def export_profiles(df: pd.DataFrame) -> None:
    if "Plant_ID" not in df.columns or "Timestamp" not in df.columns:
        raise ValueError("DataFrame must contain 'Plant_ID' and 'Timestamp'")
    df = df.dropna(subset=["Timestamp"]).sort_values("Timestamp").copy()

    for plant in df["Plant_ID"].dropna().unique():
        d0 = df[df["Plant_ID"] == plant]
        for col in SENSORS:
            if col not in d0.columns:
                continue
            d = d0[["Timestamp", col]].dropna().copy()
            if d.empty:
                continue

            # ----- daily -----
            x = d.copy()
            x["hod"] = x["Timestamp"].dt.hour
            med_hod = _safe_interp(x.groupby("hod")[col].median(), range(24))
            std_hod = x.groupby("hod")[col].std().reindex(range(24))
            std_hod = std_hod.fillna(std_hod.mean() if not np.isnan(std_hod.mean()) else 0.0)
            out = pd.DataFrame({"hod": range(24), "median": med_hod.values, "std": std_hod.values})
            (MODELS_DIR / f"daily_{plant}_{col}.csv").write_text(out.to_csv(index=False), encoding="utf-8")

            # ----- weekly -----
            if len(d) >= 24 * 7:
                xw = d.copy()
                xw["dow"] = xw["Timestamp"].dt.dayofweek
                xw["hod"] = xw["Timestamp"].dt.hour
                med_week = xw.groupby(["dow", "hod"])[col].median().unstack()
                med_week = med_week.reindex(index=range(7), columns=range(24))
                med_week = med_week.apply(lambda s: s.interpolate(limit_direction="both"), axis=1)\
                                   .interpolate(axis=0, limit_direction="both")

                std_week = xw.groupby(["dow", "hod"])[col].std().unstack()
                std_week = std_week.reindex(index=range(7), columns=range(24))
                fill_val = std_week.stack().mean() if std_week.stack().notna().any() else 0.0
                std_week = std_week.fillna(fill_val)

                med_week.reset_index(inplace=True)
                std_week.reset_index(inplace=True)
                med_week = med_week.melt(id_vars="dow", var_name="hod", value_name="median").sort_values(["dow", "hod"])
                std_week = std_week.melt(id_vars="dow", var_name="hod", value_name="std").sort_values(["dow", "hod"])
                ww = pd.merge(med_week, std_week, on=["dow","hod"], how="inner")
                (MODELS_DIR / f"weekly_{plant}_{col}.csv").write_text(ww.to_csv(index=False), encoding="utf-8")

            # ----- seasonal -----
            if d["Timestamp"].dt.year.nunique() >= 2 or len(d) >= 24 * 60:
                xs = d.copy()
                xs["doy"] = xs["Timestamp"].dt.dayofyear
                xs["hod"] = xs["Timestamp"].dt.hour
                med_doy = _safe_interp(xs.groupby("doy")[col].median(), range(1, 367))
                med_hod2 = _safe_interp(xs.groupby("hod")[col].median(), range(24))
                std_h = xs.groupby("hod")[col].std().reindex(range(24))
                std_h = std_h.fillna(std_h.mean() if not np.isnan(std_h.mean()) else 0.0)
                pd.DataFrame({"doy": range(1, 367), "median": med_doy.values})\
                    .to_csv(MODELS_DIR / f"seasonal_doy_{plant}_{col}.csv", index=False)
                pd.DataFrame({"hod": range(24), "median": med_hod2.values, "std": std_h.values})\
                    .to_csv(MODELS_DIR / f"seasonal_hod_{plant}_{col}.csv", index=False)

# ---------- Load ----------
def load_profiles(plant_id, sensor) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    p = MODELS_DIR
    daily = p / f"daily_{plant_id}_{sensor}.csv"
    weekly = p / f"weekly_{plant_id}_{sensor}.csv"
    sdoy  = p / f"seasonal_doy_{plant_id}_{sensor}.csv"
    shod  = p / f"seasonal_hod_{plant_id}_{sensor}.csv"
    if daily.exists(): out["daily"] = pd.read_csv(daily)
    if weekly.exists(): out["weekly"] = pd.read_csv(weekly)
    if sdoy.exists():  out["seasonal_doy"] = pd.read_csv(sdoy)
    if shod.exists():  out["seasonal_hod"] = pd.read_csv(shod)
    return out

# ---------- Expectation (baseline/std) ----------
def expected_from_profiles(ts: pd.Timestamp, profiles: Dict[str, pd.DataFrame]) -> Optional[Dict[str, float]]:
    if not profiles:
        return None
    ts = pd.Timestamp(ts)
    hod = int(ts.hour)
    dow = int(ts.dayofweek)
    doy = int(ts.dayofyear)

    # Seasonal: DOY + HOD
    if "seasonal_doy" in profiles and "seasonal_hod" in profiles:
        sdoy = profiles["seasonal_doy"].set_index("doy")
        shod = profiles["seasonal_hod"].set_index("hod")

        med_doy = float(sdoy.loc[doy, "median"]) if doy in sdoy.index else float(sdoy["median"].iloc[-1])
        if hod in shod.index:
            med_hod = float(shod.loc[hod, "median"])
            std_hod = float(shod.loc[hod, "std"])
        else:
            med_hod = float(shod["median"].iloc[-1])
            std_hod = float(shod["std"].mean()) if pd.notna(shod["std"].mean()) else 0.0
        if not np.isfinite(std_hod) or std_hod <= 0.0:
            std_hod = max(float(shod["std"].mean()), 1e-6)

        base = 0.5 * med_doy + 0.5 * med_hod
        return {"baseline": float(base), "band_std": float(std_hod), "bl_type": "seasonal"}

    # Weekly: DOW + HOD
    if "weekly" in profiles:
        w = profiles["weekly"].copy()
        if {"dow", "hod", "median", "std"}.issubset(set(w.columns)):
            w["dow"] = w["dow"].astype(int)
            w["hod"] = w["hod"].astype(int)
            row = w[(w["dow"] == dow) & (w["hod"] == hod)]
            if not row.empty:
                base = float(row["median"].iloc[0])
                std  = float(row["std"].iloc[0])
                if not np.isfinite(std) or std <= 0.0:
                    std = max(float(w["std"].mean()), 1e-6)
                return {"baseline": base, "band_std": std, "bl_type": "weekly"}

    # Daily: HOD only
    if "daily" in profiles:
        d = profiles["daily"].set_index("hod")
        if hod in d.index:
            base = float(d.loc[hod, "median"])
            std  = float(d.loc[hod, "std"])
        else:
            base = float(d["median"].iloc[-1])
            std  = float(d["std"].mean()) if pd.notna(d["std"].mean()) else 0.0
        if not np.isfinite(std) or std <= 0.0:
            std = max(float(d["std"].mean()), 1e-6)
        return {"baseline": base, "band_std": std, "bl_type": "daily"}

    return None

# ---------- Streaming scoring ----------
class StreamingState:
    def __init__(self, alpha: float = 2/25, bias_alpha: float = 0.002):
        self.prev_value: Optional[float] = None
        self.ema_abs_res: Optional[float] = None
        self.alpha = float(alpha)
        self.bias: float = 0.0
        self.bias_alpha: float = float(bias_alpha)

    def update_ema(self, value: float):
        if self.ema_abs_res is None:
            self.ema_abs_res = value
        else:
            self.ema_abs_res = self.alpha * value + (1 - self.alpha) * self.ema_abs_res

    def update_bias(self, residual: float):
        self.bias = (1 - self.bias_alpha) * self.bias + self.bias_alpha * residual

def score_new_point(
    ts: pd.Timestamp,
    value: float,
    profiles: Dict[str, pd.DataFrame],
    state: StreamingState,
    k_band: float = 2.0,
    spike_z_like: float = 3.0,
    break_mult: float = 1.5,
) -> Dict[str, object]:
    exp = expected_from_profiles(ts, profiles)
    if exp is None:
        return {"ok": False, "reason": "no_profiles"}

    baseline = exp["baseline"]
    band_std = exp["band_std"]
    adaptive_baseline = baseline + (state.bias or 0.0)
    lower = adaptive_baseline - k_band * band_std
    upper = adaptive_baseline + k_band * band_std
    flag_band = (value < lower) or (value > upper)

    flag_spike = False
    if state.prev_value is not None:
        diff = value - state.prev_value
        denom = band_std if band_std > 1e-9 else 1.0
        flag_spike = abs(diff) > spike_z_like * denom

    residual = value - adaptive_baseline
    state.update_ema(abs(residual))
    state.update_bias(residual) 
    flag_break = False
    if state.ema_abs_res is not None:
        flag_break = state.ema_abs_res > (break_mult * band_std)

    state.prev_value = value

    is_anomaly = flag_band or flag_spike or flag_break
    return {
        "ok": True,
        "ts": ts,
        "baseline": float(baseline),
        "adaptive_baseline": float(adaptive_baseline),
        "band_std": float(band_std),
        "lower": float(lower),
        "upper": float(upper),
        "value": float(value),
        "flags": {
            "band": bool(flag_band),
            "spike": bool(flag_spike),
            "break": bool(flag_break),
        },
        "is_anomaly": bool(is_anomaly),
        "bl_type": exp["bl_type"],
        "ema_abs_res": float(state.ema_abs_res) if state.ema_abs_res is not None else None,
        "bias": float(state.bias),
    }
