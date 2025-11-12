# src/scripts/eval_test_onnx.py
import json, numpy as np, onnxruntime as ort
from pathlib import Path
from torchvision import transforms
from torchvision.datasets import ImageFolder
from torch.utils.data import DataLoader

def load_label_mapping(path="artifacts/label_mapping.json"):
    with open(path,"r") as f:
        return json.load(f)

def preprocess_pil(img):
    tf = transforms.Compose([transforms.Resize((224,224)), transforms.ToTensor()])
    t = tf(img).numpy()
    return np.expand_dims(t, axis=0).astype(np.float32)

def run_onnx_eval(onnx_path="artifacts/model.onnx", test_dir="samples/test", batch_size=16):
    label_map = load_label_mapping()
    classes = [label_map[str(i)] for i in range(len(label_map))]
    ds = ImageFolder(test_dir, transform=None)  # we'll read PIL ourselves
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False)

    sess = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
    input_name = sess.get_inputs()[0].name
    output_name = sess.get_outputs()[0].name

    y_true, y_pred = [], []
    from PIL import Image
    for path, label in ds.samples:
        img = Image.open(path).convert("RGB")
        x = preprocess_pil(img)
        logits = sess.run([output_name], {input_name: x})[0]
        pred = int(np.argmax(logits, axis=1)[0])
        y_true.append(label)
        y_pred.append(pred)

    from sklearn.metrics import classification_report, confusion_matrix
    print(classification_report(y_true, y_pred, target_names=classes, digits=4))
    print(confusion_matrix(y_true, y_pred))

if __name__ == "__main__":
    run_onnx_eval()
