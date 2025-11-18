# tests/test_detect_residuals_and_hybrid.py
import subprocess
import sys
import pandas as pd
from pathlib import Path

def run_script(script, cwd):
    res = subprocess.run([sys.executable, "-u", script],
                         cwd=cwd, capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, f"Script failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    return res.stdout

def test_residuals_and_hybrid(synthetic_dataset):
    workdir, csv_path, n, injected_ids = synthetic_dataset
    root = Path.cwd()

    run_script(str(root / "detect_iforest_pca.py"), cwd=workdir)
    run_script(str(root / "detect_residuals_and_hybrid.py"), cwd=workdir)

    out_dir = workdir / "out"
    final_csv = out_dir / "dataset_hybrid_iforest_pca_residual.csv"
    top10_csv = out_dir / "top10_residual_rows.csv"
    hybrid_plot = out_dir / "pca_hybrid_union.png"

    assert final_csv.exists(), "Final hybrid CSV not found"
    assert top10_csv.exists(), "top10_residual_rows.csv not found"
    assert hybrid_plot.exists(), "pca_hybrid_union.png not found"

    df_final = pd.read_csv(final_csv)

    for col in ["anomaly_residual_general", "residual_general_score", "anomaly_union", "anomaly_intersection", "anomaly_2of3"]:
        assert col in df_final.columns, f"Missing column '{col}'"


    union_count = int(df_final["anomaly_union"].sum())
    assert 1 <= union_count <= 0.5 * n, f"Union anomalies seems off: {union_count}/{n}"

    
    assert "id" in df_final.columns, "id column expected"
    df_anom = df_final[df_final["anomaly_union"] == 1]
    caught = sum(1 for _id in df_anom["id"].astype(str).values if _id in injected_ids)
    assert caught >= max(1, int(0.33 * len(injected_ids))), f"Union caught too few injected anomalies: {caught}/{len(injected_ids)}"
