# detect_residuals_and_hybrid.py
# Residual-per-Feature (OOF) + Hybrid union/intersection + 2-of-3 majority
from pathlib import Path
import os
import numpy as np
import pandas as pd

# Headless plotting (WSL/CI-safe)
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from sklearn.model_selection import KFold
from sklearn.linear_model import HuberRegressor
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler
from sklearn.pipeline import Pipeline

# -------------------- Config --------------------
IN_CSV  = Path("out/dataset_with_iforest_pca.csv")  # from detect_iforest_pca.py
OUT_DIR = Path("out"); OUT_DIR.mkdir(exist_ok=True)
RANDOM_STATE = 42
N_SPLITS = 3
RES_Q = 0.85 # top 5% will be anomalies (threshold quantile)

# -------------------- Load --------------------
df = pd.read_csv(IN_CSV)


drop_derived = {
    "anomaly_iforest","iforest_score","pca_x","pca_y",
    "pca_recon_error","anomaly_pca_recon","anomaly_union","anomaly_intersection","anomaly_2of3"
}


num_cols = [c for c in df.columns
            if pd.api.types.is_numeric_dtype(df[c]) and c not in drop_derived]

df_num = df[num_cols].copy()

# -------------------- Targets --------------------

preferred_targets = [c for c in ["soil_moisture","rainfall","temperature","humidity"] if c in num_cols]
TARGETS = preferred_targets if len(preferred_targets) >= 2 else num_cols[: min(6, max(1, len(num_cols)))]

print("[INFO] Residual targets:", TARGETS)

# -------------------- Residual-per-Feature OOF  --------------------
kf = KFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
residual_mat = pd.DataFrame(0.0, index=df.index, columns=[])

for target in TARGETS:
    feats = [c for c in num_cols if c != target]
    X_full = df_num[feats].values.astype("float32")
    y_full = df_num[target].values.astype("float32")

    errs = np.zeros(len(df), dtype="float32")

    for tr, va in kf.split(X_full):
        X_tr, X_va = X_full[tr], X_full[va]
        y_tr, y_va = y_full[tr], y_full[va]

        imp  = SimpleImputer(strategy="median").fit(X_tr)
        X_tr = imp.transform(X_tr)
        X_va = imp.transform(X_va)

        scaler = RobustScaler().fit(X_tr)
        X_tr   = scaler.transform(X_tr)
        X_va   = scaler.transform(X_va)

        model = HuberRegressor(max_iter=500)
        model.fit(X_tr, y_tr)
        pred = model.predict(X_va)
        errs[va] = np.abs(pred - y_va)

    residual_mat[target] = errs

# -------------------- Residual-general OOF --------------------
general_score = residual_mat.max(axis=1)
df["residual_general_score"] = general_score

thr = float(np.quantile(general_score, RES_Q))
df["anomaly_residual_general"] = (general_score >= thr).astype(int)
print(f"[INFO] Residual-general anomalies: {int(df['anomaly_residual_general'].sum())} "
      f"({df['anomaly_residual_general'].mean()*100:.1f}%), thr={thr:.6f}")

# -------------------- Hybrid: Union / Intersection / 2-of-3 --------------------
methods = []
if "anomaly_iforest" in df.columns:   methods.append("anomaly_iforest")
if "anomaly_pca_recon" in df.columns: methods.append("anomaly_pca_recon")
methods.append("anomaly_residual_general")

df["anomaly_union"] = df[methods].max(axis=1)
df["anomaly_intersection"] = (df[methods].sum(axis=1) == len(methods)).astype(int)
votes = df[methods].sum(axis=1)
df["anomaly_2of3"] = (votes >= 2).astype(int)
print(f"[INFO] Hybrid 2-of-3: {int(df['anomaly_2of3'].sum())} ({df['anomaly_2of3'].mean()*100:.1f}%)")

print("[INFO] Hybrid summary:")
for m in methods + ["anomaly_union","anomaly_intersection"]:
    print(f"  {m}: {int(df[m].sum())} ({df[m].mean()*100:.1f}%)")

# -------------------- TOP-10 --------------------
try:
    top10_idx = df["residual_general_score"].nlargest(min(10, len(df))).index
    cols_to_show = ["residual_general_score","anomaly_residual_general"] + \
                   [c for c in ["soil_moisture","rainfall","temperature","humidity"] if c in df.columns]
    top10 = df.loc[top10_idx, cols_to_show].copy()
except Exception:
    top10 = pd.DataFrame(columns=["residual_general_score","anomaly_residual_general"])
top10.to_csv(OUT_DIR/"top10_residual_rows.csv", index=False)

# -------------------- Plot: PCA 2D colored by Hybrid union --------------------
if {"pca_x","pca_y"}.issubset(df.columns):
    plt.figure(figsize=(7,6))
    mask = df["anomaly_union"].astype(bool)
    plt.scatter(df.loc[~mask,"pca_x"], df.loc[~mask,"pca_y"], s=12, alpha=0.25, label="normal")
    plt.scatter(df.loc[mask, "pca_x"],  df.loc[mask, "pca_y"],  s=20, alpha=0.9, marker="x", label="anomaly (union)")
    plt.title("PCA (2D) colored by HYBRID (union)")
    plt.xlabel("PC1"); plt.ylabel("PC2"); plt.legend(); plt.tight_layout()
    plt.savefig(OUT_DIR/"pca_hybrid_union.png"); plt.close()

# -------------------- Save batch outputs --------------------
out_csv = OUT_DIR/"dataset_hybrid_iforest_pca_residual.csv"
df.to_csv(out_csv, index=False)
print("[INFO] Saved CSV ->", out_csv.resolve())
print("[INFO] Saved plots/results in:", OUT_DIR.resolve())

# -------------------- Build residual models for serving (Flink) --------------------

residual_models_by_target = {}
numeric_feature_names = list(num_cols)
for target in TARGETS:
    feats = [c for c in num_cols if c != target]
    X_full = df_num[feats].values.astype("float32")
    y_full = df_num[target].values.astype("float32")
    pipe = Pipeline([
        ("imp", SimpleImputer(strategy="median")),
        ("sc",  RobustScaler()),
        ("hub", HuberRegressor(max_iter=500))
    ])
    pipe.fit(X_full, y_full)
    residual_models_by_target[target] = [pipe]

residual_error_threshold = float(thr) 

# -------------------- Persist artifacts for streaming (Flink) --------------------
import joblib
MODEL_VERSION = os.getenv("MODEL_VERSION_RESID", "resid-1")
Path("models").mkdir(exist_ok=True)

artifact_resid = {
    "model_version": MODEL_VERSION,
    "resid_models":  residual_models_by_target,  
    "resid_thr":     residual_error_threshold,  
    "num_cols":      numeric_feature_names,       
}

out_path_resid = "models/residuals_artifacts.joblib"
joblib.dump(artifact_resid, out_path_resid)
print(f"✅ saved: {out_path_resid} (version={MODEL_VERSION})")