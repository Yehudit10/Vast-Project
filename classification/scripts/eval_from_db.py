# English-only file.
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import psycopg2
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    confusion_matrix,
    classification_report,
)

# Default to your 11-class taxonomy (excluding "another").
DEFAULT_LABELS = [
    "predatory_animals",
    "non_predatory_animals",
    "birds",
    "fire",
    "footsteps",
    "insects",
    "screaming",
    "shotgun",
    "stormy_weather",
    "streaming_water",
    "vehicle",
]

def infer_true_label_from_path(p: str, valid: List[str]) -> Optional[str]:
    """
    Infer ground-truth label from file path by looking for the class folder name.
    Returns one of 'valid', or None if not found.
    """
    parts = [x.lower() for x in pathlib.Path(p).parts]
    for c in valid:
        if c.lower() in parts:
            return c
    return None

def parse_labels_arg(s: Optional[str]) -> List[str]:
    if not s:
        return DEFAULT_LABELS
    labels = [x.strip() for x in s.split(",") if x.strip()]
    return labels if labels else DEFAULT_LABELS

def fetch_joined_rows(conn, last: int) -> pd.DataFrame:
    """
    Load file-level aggregates joined with files and runs.
    Uses flexible JSON column: head_probs_json.
    """
    q = f"""
    SELECT
      r.run_id,
      r.model_name,
      r.window_sec,
      r.hop_sec,
      r.pad_last,
      r.agg,
      COALESCE(r.notes, '') AS notes,
      f.path AS file_path,
      fa.head_probs_json,
      fa.head_pred_label,
      fa.head_pred_prob,
      fa.head_is_another,
      fa.num_windows,
      fa.agg_mode
    FROM file_aggregates fa
    JOIN files f ON f.file_id = fa.file_id
    JOIN runs  r ON r.run_id  = fa.run_id
    WHERE r.run_id IN (
      SELECT run_id
      FROM runs
      ORDER BY started_at DESC
      LIMIT %s
    )
    ORDER BY r.run_id, f.path;
    """
    with conn.cursor() as cur:
        cur.execute(q, (int(last),))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return pd.DataFrame(rows, columns=cols)

def extract_probs_map(obj: object) -> Dict[str, float]:
    """
    Normalize JSON to {label: prob} dict of floats.
    """
    if obj is None:
        return {}
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except Exception:
            return {}
    if isinstance(obj, dict):
        out: Dict[str, float] = {}
        for k, v in obj.items():
            try:
                out[str(k)] = float(v)
            except Exception:
                continue
        return out
    return {}

def probs_to_pred(probs: Dict[str, float], labels: List[str]) -> Tuple[Optional[str], Optional[float]]:
    """
    Choose argmax label among 'labels'. If none present, return (None, None).
    """
    vals = [(lbl, probs.get(lbl, float("-inf"))) for lbl in labels]
    vals_sorted = sorted(vals, key=lambda x: x[1], reverse=True)
    if not vals_sorted or not np.isfinite(vals_sorted[0][1]):
        return None, None
    return vals_sorted[0][0], float(vals_sorted[0][1])

def evaluate_one_run(df_run: pd.DataFrame, labels: List[str], ignore_another: bool) -> Tuple[pd.DataFrame, Dict[str, float], np.ndarray]:
    """
    Compute metrics for a single run. Returns:
      - df_eval: per-file rows with y_true/y_pred and per-class probs
      - summary: dict metrics
      - cm: confusion matrix (labels order as provided)
    """
    df = df_run.copy()

    # Ground-truth from path
    df["y_true"] = df["file_path"].apply(lambda p: infer_true_label_from_path(str(p), labels))

    # Parse JSON probs and choose prediction
    probs_list: List[Dict[str, float]] = []
    preds: List[Optional[str]] = []
    pred_probs: List[Optional[float]] = []
    for _, row in df.iterrows():
        pm = extract_probs_map(row.get("head_probs_json"))
        probs_list.append(pm)
        # Prefer DB's final decision when it's not "another"
        db_pred = row.get("head_pred_label")
        db_p    = row.get("head_pred_prob")
        db_is_another = bool(row.get("head_is_another"))
        if (isinstance(db_pred, str)) and (db_pred in labels) and (not db_is_another):
            preds.append(db_pred)
            pred_probs.append(float(db_p) if db_p is not None else None)
        else:
            p_lbl, p_val = probs_to_pred(pm, labels)
            preds.append(p_lbl)
            pred_probs.append(p_val)

    df["y_pred"] = preds
    df["y_pred_prob"] = pred_probs

    # Expand per-class columns for CSV
    for c in labels:
        df[f"p_{c}"] = [pm.get(c) if pm else None for pm in probs_list]

    # Optionally drop rows marked as "another" (low confidence fallback)
    if ignore_another:
        df = df[~df["y_pred"].isna()].copy()  # already ensured not "another"
    # Drop rows with missing truth or pred not in label set
    df = df[df["y_true"].isin(labels)].copy()
    df = df[df["y_pred"].isin(labels)].reset_index(drop=True)

    if df.empty:
        return df, {
            "accuracy": np.nan,
            "precision_macro": np.nan,
            "recall_macro": np.nan,
            "f1_macro": np.nan,
            "support": 0,
            "coverage_final": 0.0,
        }, np.zeros((len(labels), len(labels)), dtype=int)

    y_true = df["y_true"].to_numpy()
    y_pred = df["y_pred"].to_numpy()

    acc = accuracy_score(y_true, y_pred)
    p_macro, r_macro, f1_macro, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, average="macro", zero_division=0
    )
    cm = confusion_matrix(y_true, y_pred, labels=labels)

    # coverage_final: how many files did not end up as "another" in DB decision?
    # We compute it from the original df_run (before drops).
    n_total = len(df_run)
    n_final = int((~df_run["head_is_another"].fillna(False)).sum())
    coverage = float(n_final) / float(n_total) if n_total > 0 else 0.0

    summary = {
        "accuracy": float(acc),
        "precision_macro": float(p_macro),
        "recall_macro": float(r_macro),
        "f1_macro": float(f1_macro),
        "support": int(len(y_true)),
        "coverage_final": coverage,
    }
    return df, summary, cm

def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate file-level results per run from PostgreSQL and export metrics.")
    ap.add_argument("--db-url", default=os.getenv("DB_URL"), help="PostgreSQL URL (e.g. postgres://user:pass@host:5432/db)")
    ap.add_argument("--schema", default=os.getenv("DB_SCHEMA", "audio_cls"))
    ap.add_argument("--last", type=int, default=12, help="How many latest runs to include")
    ap.add_argument("--labels", default=None, help="Comma-separated label list to evaluate; default = 11-class taxonomy")
    ap.add_argument("--ignore-another", action="store_true", default=True, help="Ignore rows whose final decision was 'another'")
    ap.add_argument("--out-dir", default="eval_reports", help="Directory to write CSV summaries and confusion matrices")
    args = ap.parse_args()

    if not args.db_url:
        print("[error] --db-url or env DB_URL is required", file=sys.stderr)
        sys.exit(2)

    labels = parse_labels_arg(args.labels)
    os.makedirs(args.out_dir, exist_ok=True)

    conn = psycopg2.connect(args.db_url)
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {args.schema}, public;")
    conn.commit()

    try:
        df_all = fetch_joined_rows(conn, last=int(args.last))
    finally:
        conn.close()

    if df_all.empty:
        print("[warn] No joined rows found (file_aggregates × files × runs). Did you run classify with --write-db?")
        sys.exit(0)

    summaries: List[Dict[str, object]] = []
    for run_id, df_run in df_all.groupby("run_id", sort=False):
        meta = df_run.iloc[0][["model_name", "window_sec", "hop_sec", "pad_last", "agg", "notes"]].to_dict()
        df_eval, summary, cm = evaluate_one_run(df_run, labels=labels, ignore_another=bool(args.ignore_another))

        # Save per-file evaluation
        per_file_csv = os.path.join(args.out_dir, f"per_file_{run_id}.csv")
        base_cols = ["file_path", "y_true", "y_pred", "y_pred_prob", "head_pred_label", "head_pred_prob", "head_is_another"]
        prob_cols = [f"p_{c}" for c in labels]
        keep_cols = [c for c in base_cols if c in df_eval.columns] + prob_cols
        df_eval[keep_cols].to_csv(per_file_csv, index=False)

        # Save confusion matrix
        cm_csv = os.path.join(args.out_dir, f"confusion_{run_id}.csv")
        cm_df = pd.DataFrame(cm, index=labels, columns=labels)
        cm_df.to_csv(cm_csv)

        # Compose run summary row
        row = {
            "run_id": run_id,
            **meta,
            **summary,
            "n_files_evaluated": int(len(df_eval)),
            "per_file_csv": per_file_csv,
            "confusion_csv": cm_csv,
        }
        summaries.append(row)

    # Write summary CSV
    summary_df = pd.DataFrame(summaries)
    summary_csv = os.path.join(args.out_dir, "runs_summary.csv")
    summary_df.to_csv(summary_csv, index=False)

    # Also show a compact table on stdout
    disp_cols = [
        "run_id", "model_name", "window_sec", "hop_sec", "pad_last", "agg",
        "accuracy", "precision_macro", "recall_macro", "f1_macro", "coverage_final", "n_files_evaluated"
    ]
    show_cols = [c for c in disp_cols if c in summary_df.columns]
    print("\n=== Run-level summary ===")
    if not summary_df.empty:
        print(summary_df[show_cols].to_string(index=False))
    print(f"\n[info] Wrote run-level summary to: {summary_csv}")
    print(f"[info] Per-run files and confusion matrices are in: {args.out_dir}")

if __name__ == "__main__":
    main()
