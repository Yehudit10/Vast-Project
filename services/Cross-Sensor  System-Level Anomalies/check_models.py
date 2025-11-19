import joblib

print("=== iforest_pca_artifacts.joblib ===")
try:
    artifact_ifpca = joblib.load("models/iforest_pca_artifacts.joblib")
    print("Model version:", artifact_ifpca.get("model_version"))
    print("PCA threshold:", artifact_ifpca.get("pca_thr"))
    print("Features:", artifact_ifpca.get("feature_cols", [])[:5], "...")
except Exception as e:
    print("Error loading iforest_pca_artifacts.joblib:", e)

print("\n=== residuals_artifacts.joblib ===")
try:
    artifact_resid = joblib.load("models/residuals_artifacts.joblib")
    print("Model version:", artifact_resid.get("model_version"))
    print("Residual threshold:", artifact_resid.get("resid_thr"))
    print("Targets:", list(artifact_resid.get("resid_models", {}).keys()))
except Exception as e:
    print("Error loading residuals_artifacts.joblib:", e)
