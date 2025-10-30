# eval_alerts.py
from pathlib import Path
import csv

def has_label(lbl_path: Path) -> bool:
    if not lbl_path.exists():
        return False
    txt = lbl_path.read_text(encoding="utf-8", errors="ignore").strip()
    return bool(txt)

def main():
    alerts_csv = Path("runs_fence/y8n_baseline_vote_soft/alerts.csv")  # עדכני נתיב אם שונה
    labels_dir = Path("data/fence_holes/valid/labels")

    rows=[]
    with alerts_csv.open("r", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            idx = int(r["index"])
            img = Path(r["image"])
            fired = int(r["fired_alert"])  # 1/0
            # קובץ label בהתאם לשם התמונה:
            lbl = labels_dir / f"{img.stem}.txt"
            gt = has_label(lbl)
            rows.append((idx, gt, fired))

    TP=FP=FN=TN=0
    for _, gt, fired in rows:
        if fired==1 and gt:
            TP += 1
        elif fired==1 and not gt:
            FP += 1
        elif fired==0 and gt:
            FN += 1
        else:
            TN += 1

    prec = TP / (TP + FP + 1e-9)
    rec  = TP / (TP + FN + 1e-9)
    f1   = 2*prec*rec/(prec+rec+1e-9)

    print(f"alerts: TP={TP} FP={FP} FN={FN} TN={TN}")
    print(f"Precision={prec:.3f} Recall={rec:.3f} F1={f1:.3f}")

if __name__ == "__main__":
    main()
