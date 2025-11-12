import argparse, os, base64, time, json, glob
import requests

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images-dir", required=True)
    ap.add_argument("--api", default="http://localhost:8000")
    args = ap.parse_args()

    # Collect all images
    imgs = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
        imgs += glob.glob(os.path.join(args.images_dir, '**', ext), recursive=True)
    imgs = sorted(imgs)

    if not imgs:
        print("No images found in", args.images_dir)
        return

    for path in imgs:
        filename = os.path.basename(path)

        # IMPORTANT: The device_id must be encoded inside the filename,
        # e.g.   device123_20250101T1030.jpg
        print(f"Sending {filename} ...")

        try:
            with open(path, "rb") as f:
                files = {"image": (filename, f)}
                r = requests.post(
                    args.api + "/infer",
                    files=files,
                    timeout=60
                )

            if r.status_code != 200:
                print("Error:", r.status_code, r.text)
            else:
                print(json.dumps(r.json(), indent=2))

        except Exception as e:
            print("Request failed:", e)

        time.sleep(0.4)


if __name__ == "__main__":
    main()
