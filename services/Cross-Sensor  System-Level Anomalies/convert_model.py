import joblib
import sys
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: python convert_model.py <model_file.pkl>")
        sys.exit(1)

    model_path = Path(sys.argv[1])
    if not model_path.exists():
        print(f"❌ File not found: {model_path}")
        sys.exit(1)


    print(f"📥 Loading model from {model_path} ...")
    model = joblib.load(model_path)


    new_path = model_path.with_name(model_path.stem + "_compat.pkl")

   
    joblib.dump(model, new_path)

    print(f"✅ Model re-saved successfully as {new_path}")

if __name__ == "__main__":
    main()
