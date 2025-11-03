# scripts/extract_mistakes.py
import json, csv, shutil
from pathlib import Path

def gt_from_path(p: Path) -> str:
    s = "/".join([part.lower() for part in p.parts])
    if ("healthy" in s) or ("fresh" in s):
        return "ok"
    for k in ["rotten","defect","mold","mould","bad","decay","damaged","spoiled"]:
        if k in s:
            return "defect"
    return "ok"

def main():
    infer_json = Path("outputs/infer_results.json")
    if not infer_json.exists():
        raise SystemExit("לא נמצא outputs/infer_results.json. תריצי קודם את האינפרנס: python inference/infer_fruit_defect.py")

    with open(infer_json, "r", encoding="utf-8") as f:
        results = json.load(f)

    mistakes_dir = Path("outputs/mistakes")
    fp_dir = mistakes_dir / "fp"  # False Positive: GT=ok, Pred=defect
    fn_dir = mistakes_dir / "fn"  # False Negative: GT=defect, Pred=ok
    for d in [fp_dir, fn_dir]:
        d.mkdir(parents=True, exist_ok=True)

    rows = []
    tp = tn = fp = fn = 0

    for r in results:
        p = Path(r["path"])
        pred = r["status"]  # "ok" / "defect"
        gt = gt_from_path(p)

        if gt == "defect" and pred == "defect":
            tp += 1
        elif gt == "ok" and pred == "ok":
            tn += 1
        elif gt == "ok" and pred == "defect":
            fp += 1
            out_name = f"FP_pred-defect_gt-ok_{p.name}"
            shutil.copy2(p, fp_dir / out_name)
            rows.append([str(p), gt, pred, "FP"])
        elif gt == "defect" and pred == "ok":
            fn += 1
            out_name = f"FN_pred-ok_gt-defect_{p.name}"
            shutil.copy2(p, fn_dir / out_name)
            rows.append([str(p), gt, pred, "FN"])

    mistakes_dir.mkdir(parents=True, exist_ok=True)
    csv_path = mistakes_dir / "mistakes.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path","gt","pred","type"])
        w.writerows(rows)

    total = tp + tn + fp + fn
    acc = (tp + tn) / total if total else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2*prec*rec/(prec+rec) if (prec+rec) else 0.0

    print("\nConfusion Matrix (based on infer_results.json paths)")
    print(f"TP={tp}  FP={fp}")
    print(f"FN={fn}  TN={tn}")
    print(f"\nacc={acc:.4f}  precision={prec:.4f}  recall={rec:.4f}  f1={f1:.4f}")
    print(f"\nWrote mistakes CSV: {csv_path}")
    print(f"Copied FP -> {fp_dir}")
    print(f"Copied FN -> {fn_dir}")

if __name__ == "__main__":
    main()
