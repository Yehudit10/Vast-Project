# classify.py
import argparse
import pathlib
import sys
import numpy as np
import soundfile as sf
import librosa
from panns_inference import AudioTagging
from labels_map import bucket_of

import os
import urllib.request

SAMPLE_RATE = 32000  # מומלץ ל-PANNs

def ensure_checkpoint(checkpoint_path: str, checkpoint_url: str | None) -> str:
    """
    Make sure there is a weight file available. If there is a URL, download it with urllib (no get).
    Returns the final route.
    """
    p = pathlib.Path(checkpoint_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        return str(p)

    if not checkpoint_url:
        raise FileNotFoundError(
            f"No checkpoint found in: {p}. Provider-- checkpoint or-- checkpoint-URL."
        )

    print(f"[info] Downloading weights:\nURL: {checkpoint_url}\nTo: {p}")
    urllib.request.urlretrieve(checkpoint_url, p)
    print("[info] Download complete.")
    return str(p)

def load_audio(path: str, target_sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Audio loader, Lamono converter, resample to 32 kHz, and returns np.float32 in the range [-1, 1].
    """
    y, sr = sf.read(path, always_2d=False)
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    if sr != target_sr:
        y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
    y = y.astype(np.float32, copy=False)
    return y

def softmax(x: np.ndarray) -> np.ndarray:
    x = x - np.max(x)
    e = np.exp(x)
    return e / np.sum(e)

def summarize_buckets(topk_labels: list[tuple[str, float]]) -> dict:
    """
    Group probabilities by 4 buckets by schema the probabilities of tags that fell to each bucket.
    """
    sums = {"animal": 0.0, "vehicle": 0.0, "shotgun": 0.0, "other": 0.0}
    for label, prob in topk_labels:
        b = bucket_of(label)
        sums[b] += prob
    # נרמול ל-1 אם יש סטייה
    total = sum(sums.values())
    if total > 0:
        for k in sums:
            sums[k] /= total
    return sums

def main():
    ap = argparse.ArgumentParser(description="Baseline CNN14 classifier (print only)")
    ap.add_argument("--audio", required=True, help="קובץ wav/flac/mp3 וכו' או תיקייה")
    ap.add_argument("--checkpoint", default=str(pathlib.Path.home() / "panns_data" / "Cnn14_mAP=0.431.pth"),
                    help="נתיב לקובץ המשקלות (מקומי). ברירת מחדל: ~/panns_data/Cnn14_mAP=0.431.pth")
    ap.add_argument("--checkpoint-url", default=None,
                    help="אם אין קובץ מקומי – URL שממנו להוריד את המשקלות (יוריד עם urllib).")
    ap.add_argument("--topk", type=int, default=10, help="כמה תגיות מפורטות להציג")
    args = ap.parse_args()

    audio_path = pathlib.Path(args.audio)

    # הבטחת משקלות
    try:
        ckpt = ensure_checkpoint(args.checkpoint, args.checkpoint_url)
    except Exception as e:
        print(f"[error] I couldn't make weights: {e}")
        sys.exit(1)

    # יצירת מודל
    # AudioTagging ידע לטעון את המשקלות אם נצביע לו עליהן.
    at = AudioTagging(checkpoint_path=ckpt, device="cpu")  # CPU ב־Windows זה הכי יציב

    # קיבוץ קבצים
    files = []
    if audio_path.is_dir():
        for ext in ("*.wav", "*.mp3", "*.flac", "*.ogg", "*.m4a"):
            files.extend(sorted(audio_path.glob(ext)))
    else:
        files = [audio_path]

    if not files:
        print(f"[warn] No audio files were found under {audio_path}")
        sys.exit(0)

    for f in files:
        try:
            wav = load_audio(str(f), target_sr=SAMPLE_RATE)  # np.float32 מונו 32k
            # הממשק של panns-inference מקבל waveform ו-sr
            # חוזר dict עם 'clipwise_output' ו'התגיות'
            res = at.inference(waveform=wav[None, :], sr=SAMPLE_RATE)  # צורה (1, T)

            # קבלת וקטור הסתברויות + רשימת תגים
            clipwise = res["clipwise_output"][0]  # np.ndarray צף
            labels = res["labels"]
            probs = softmax(clipwise)  # הבטחת נרמול (לעתים לא הכרחי, אבל נוח)

            # מיון והדפסה
            idx_sorted = np.argsort(probs)[::-1]
            topk = idx_sorted[:args.topk]
            topk_pairs = [(labels[i], float(probs[i])) for i in topk]

            print(f"\n========== {f.name} ==========")
            print("Top predictions:")
            for i, (lab, p) in enumerate(topk_pairs, 1):
                print(f"{i:2d}. {lab:40s} {p:7.4f}")

            buckets = summarize_buckets(topk_pairs)
            print("\nCoarse buckets (normalized from top-k):")
            for k in ("animal", "vehicle", "shotgun", "other"):
                print(f"- {k:<8} {buckets[k]:7.4f}")

        except Exception as e:
            print(f"[error] I failed on {f}: {e}")

if __name__ == "__main__":
    main()
