import json
from pathlib import Path
from PIL import Image, ImageDraw

def json_to_mask(json_path: Path, out_dir: Path):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    H, W = data["imageHeight"], data["imageWidth"]
    mask = Image.new("L", (W, H), 0)  # מסכה שחורה
    draw = ImageDraw.Draw(mask)

    for shape in data["shapes"]:
        points = [(x, y) for x, y in shape["points"]]
        draw.polygon(points, outline=255, fill=255)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / (json_path.stem + ".png")
    mask.save(out_path)

def convert_dir(src_dir: str, dst_dir: str):
    src = Path(src_dir)
    dst = Path(dst_dir)
    dst.mkdir(parents=True, exist_ok=True)

    for json_file in src.glob("*.json"):
        json_to_mask(json_file, dst)

if __name__ == "__main__":
    base = Path(r"C:\Users\משתמש\Desktop\vectordb\fruit-defect\Datasets\Strawberry Disease Detection Dataset")

    convert_dir(base / "train", base / "train_masks")
    convert_dir(base / "val", base / "val_masks")
    convert_dir(base / "test", base / "test_masks")

    print("✅ Done! masks created.")
