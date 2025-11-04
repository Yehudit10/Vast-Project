import onnxruntime as ort, numpy as np
from PIL import Image
from torchvision import transforms
IMAGENET_MEAN=(0.485,0.456,0.406); IMAGENET_STD=(0.229,0.224,0.225)
classes=["unripe","ripe","overripe"]
tfm = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(224),
                          transforms.ToTensor(), transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)])

def predict(path, onnx_path="ripeness_mobilenet_v3.onnx"):
    img = tfm(Image.open(path).convert("RGB")).unsqueeze(0).numpy()
    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    logits = sess.run(["logits"], {"images": img})[0]
    prob = np.exp(logits - logits.max()) / np.exp(logits - logits.max()).sum(axis=1, keepdims=True)
    return classes[int(prob.argmax(1))], prob[0]

if __name__ == "__main__":
    import sys
    label, p = predict(sys.argv[1])
    print(label, p)
