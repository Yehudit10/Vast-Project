# detect_iforest_pca.py
from pathlib import Path
import numpy as np
import pandas as pd

# WSL/Headless-safe plotting
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import RobustScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import IsolationForest
from sklearn.decomposition import PCA

# -------------------- Config --------------------
CSV_PATH = Path("data/Crop_recommendationV2.csv") 
OUT_DIR  = Path("out"); OUT_DIR.mkdir(exist_ok=True)

CONTAMINATION = 0.15   # the proportion of anomalies in the data
N_ESTIMATORS  = 300
RANDOM_STATE  = 42 


EXCLUDE_COLS = {"label","crop","target","index"}

# -------------------- Load & normalize --------------------
df = pd.read_csv(CSV_PATH)

if "id" not in df.columns:
    df.insert(0, "id", df.index.astype(str))

df.columns = (df.columns
              .str.strip().str.lower()
              .str.replace(" ", "_")
              .str.replace("%", "pct")
              .str.replace(r"[^0-9a-zA-Z_]", "", regex=True))

candidate_cols = [c for c in df.columns if c not in EXCLUDE_COLS]
num_cols = [c for c in candidate_cols if pd.api.types.is_numeric_dtype(df[c])]
cat_cols = [c for c in candidate_cols
            if pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_categorical_dtype(df[c])]

numeric_pipeline = Pipeline([
    ("impute", SimpleImputer(strategy="median")),
    ("scale",  RobustScaler())
])
categorical_pipeline = Pipeline([
    ("impute", SimpleImputer(strategy="most_frequent")),
    ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))
])
pre = ColumnTransformer(
    transformers=[
        ("num", numeric_pipeline, num_cols),
        ("cat", categorical_pipeline, cat_cols)
    ],
    remainder="drop"
)

X = pre.fit_transform(df) 

# -------------------- Isolation Forest --------------------
iso = IsolationForest(
    n_estimators=N_ESTIMATORS,
    contamination=CONTAMINATION,
    random_state=RANDOM_STATE
)
pred = iso.fit_predict(X)           # 1=normal, -1=anomaly
score = -iso.decision_function(X) 

df["anomaly_iforest"] = (pred == -1).astype(int)
df["iforest_score"]   = score

# -------------------- PCA (2D) --------------------
pca2 = PCA(n_components=2, random_state=RANDOM_STATE)
Z = pca2.fit_transform(X)
df["pca_x"] = Z[:,0]; df["pca_y"] = Z[:,1]

plt.figure(figsize=(7,6))
mask = df["anomaly_iforest"].astype(bool)
plt.scatter(df.loc[~mask,"pca_x"], df.loc[~mask,"pca_y"], s=12, alpha=0.25, label="normal")
plt.scatter(df.loc[mask,"pca_x"],  df.loc[mask, "pca_y"],  s=20, alpha=0.9, marker="x", label="anomaly")
plt.title("PCA (2D) projection with IsolationForest anomalies")
plt.xlabel("PC1"); plt.ylabel("PC2"); plt.legend(); plt.tight_layout()
plt.savefig(OUT_DIR/"pca_iforest_anomalies.png"); plt.close()

# -------------------- PCA Reconstruction Error --------------------
pca_full   = PCA(n_components=0.90, svd_solver="full", random_state=RANDOM_STATE)
Zf         = pca_full.fit_transform(X)
X_recon    = pca_full.inverse_transform(Zf)
recon_err  = np.mean((X - X_recon)**2, axis=1)

df["pca_recon_error"] = recon_err
PCA_ERR_Q = 0.85 # top 5% will be anomalies
thr = np.quantile(recon_err, PCA_ERR_Q)
df["anomaly_pca_recon"] = (recon_err >= thr).astype(int)

# -------------------- Union / Intersection --------------------
df["anomaly_union"]        = df[["anomaly_iforest","anomaly_pca_recon"]].max(axis=1)
df["anomaly_intersection"] = (df[["anomaly_iforest","anomaly_pca_recon"]].sum(axis=1) == 2).astype(int)

# -------------------- Save --------------------
out_csv = OUT_DIR/"dataset_with_iforest_pca.csv"
df.to_csv(out_csv, index=False)
print("[INFO] Saved CSV ->", out_csv.resolve())
print("[INFO] Summary:")
for col in ["anomaly_iforest","anomaly_pca_recon","anomaly_union","anomaly_intersection"]:
    print(f"  {col}: {int(df[col].sum())} ({df[col].mean()*100:.1f}%)")
print("[INFO] Plots saved in:", OUT_DIR.resolve())
# === Persist trained artifacts for streaming (Flink) ===
import os
import joblib
import pathlib

MODEL_VERSION = os.getenv("MODEL_VERSION_IFPCA", "ifpca-1")
pathlib.Path("models").mkdir(exist_ok=True)

artifact_ifpca = {
    "model_version": MODEL_VERSION,
    "pre":           pre,              
    "iforest":       iso,           
    "pca":           pca_full,          
    "pca_thr":       float(thr),       
    "feature_cols":  list(candidate_cols), 
    "num_cols":      list(num_cols),       
}

out_path_ifpca = "models/iforest_pca_artifacts.joblib"
joblib.dump(artifact_ifpca, out_path_ifpca)
print(f"✅ saved: {out_path_ifpca} (version={MODEL_VERSION})")