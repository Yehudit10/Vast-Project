# tests/test_detect_iforest_pca.py
import subprocess
import sys
import pandas as pd
from pathlib import Path

def run_script(script, cwd):
    res = subprocess.run([sys.executable, "-u", script],
                         cwd=cwd, capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, f"Script failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    return res.stdout

def test_iforest_pca_pipeline(synthetic_dataset):
    workdir, csv_path, n, injected_ids = synthetic_dataset

    root = Path.cwd()
    assert (root / "detect_iforest_pca.py").exists()
    assert (root / "detect_residuals_and_hybrid.py").exists()

    run_script(str(root / "detect_iforest_pca.py"), cwd=workdir)

    out_dir = workdir / "out"
    assert out_dir.exists(), "out/ not created"

    out_csv = out_dir / "dataset_with_iforest_pca.csv"
    pca_plot = out_dir / "pca_iforest_anomalies.png"
    assert out_csv.exists(), "dataset_with_iforest_pca.csv not found"
    assert pca_plot.exists(), "pca_iforest_anomalies.png not found"

    df_out = pd.read_csv(out_csv)
    required_cols = {
        "anomaly_iforest", "iforest_score",
        "pca_x", "pca_y",
        "pca_recon_error", "anomaly_pca_recon",
        "anomaly_union", "anomaly_intersection"
    }
    assert required_cols.issubset(df_out.columns), f"Missing columns: {required_cols - set(df_out.columns)}"
    assert len(df_out) == n, "Row count changed unexpectedly"


    if_count = int(df_out["anomaly_iforest"].sum())
    expected = 0.10 * n
    assert abs(if_count - expected) <= 0.05 * n, f"IF anomalies off expected ~10%: got {if_count}/{n}"


    pca_count = int(df_out["anomaly_pca_recon"].sum())
    assert 1 <= pca_count <= 0.2 * n, f"PCA recon anomalies looks off: {pca_count}"
