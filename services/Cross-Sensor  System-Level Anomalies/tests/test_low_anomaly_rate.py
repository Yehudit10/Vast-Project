# tests/test_low_anomaly_rate.py
import subprocess, sys, pandas as pd
from pathlib import Path

def run(script, cwd):
    res = subprocess.run([sys.executable, "-u", script],
                         cwd=cwd, capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, f"Script failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    return res.stdout

def test_clean_dataset_has_low_flags(no_anomaly_dataset_tmpdir):
    workdir, n, injected = no_anomaly_dataset_tmpdir
    root = Path.cwd()

    run(str(root / "detect_iforest_pca.py"), cwd=workdir)
    run(str(root / "detect_residuals_and_hybrid.py"), cwd=workdir)

    df = pd.read_csv(workdir / "out" / "dataset_hybrid_iforest_pca_residual.csv")

    if_rate  = df["anomaly_iforest"].mean()
    pca_rate = df["anomaly_pca_recon"].mean()
    res_rate = df["anomaly_residual_general"].mean()
    two_of_three_rate = df["anomaly_2of3"].mean()

    msg = (f"Too many 2/3 anomalies on a clean dataset: {two_of_three_rate:.3f} "
           f"(IF={if_rate:.3f}, PCA={pca_rate:.3f}, RES={res_rate:.3f})")

    assert two_of_three_rate < 0.07, msg
