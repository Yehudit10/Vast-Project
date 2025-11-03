from fastapi import FastAPI, UploadFile, File, Query
import onnxruntime as ort, numpy as np, torch
from PIL import Image
from torchvision import transforms

IMAGENET_MEAN=(0.485,0.456,0.406); IMAGENET_STD=(0.229,0.224,0.225)
FRUITS   = ["apple","banana","orange","pineapple"]
RIPENESS = ["unripe","ripe","overripe"]
TFM = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(224),
                          transforms.ToTensor(), transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])

app = FastAPI(title="Ripeness Conditional Service")
sess = ort.InferenceSession("ripeness_conditional.onnx", providers=["CPUExecutionProvider"])

def softmax(x):
    x = x - x.max(axis=1, keepdims=True); e = np.exp(x); return e / e.sum(axis=1, keepdims=True)

@app.post("/predict")
async def predict(file: UploadFile = File(...), fruit: str = Query(..., description="apple|banana|orange|pineapple")):
    fruit = fruit.lower()
    if fruit not in FRUITS:
        return {"error": f"fruit must be one of {FRUITS}"}
    img = Image.open(await file.read()).convert("RGB")
    x = TFM(img).unsqueeze(0).numpy()
    fidx = np.array([FRUITS.index(fruit)], dtype=np.int64)
    logits = sess.run(["ripeness_logits"], {"images": x, "fruit_idx": fidx})[0]
    prob = softmax(logits)[0]; idx = int(prob.argmax())
    return {"fruit": fruit, "ripeness_pred": RIPENESS[idx],
            "probs": {RIPENESS[i]: float(prob[i]) for i in range(len(RIPENESS))}}
