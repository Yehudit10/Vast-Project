import json
import numpy as np
import onnxruntime as ort
from typing import List
from PIL import Image
from .utils import preprocess_onnx

class ONNXMoistureModel:
    def __init__(self, model_path: str, label_map_path: str):
        self.sess = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        with open(label_map_path, "r", encoding="utf-8") as f:
            self.label_map = json.load(f)  # index -> label
        self.input_name = self.sess.get_inputs()[0].name
        self.output_name = self.sess.get_outputs()[0].name

    def predict_proba_patch(self, patch: Image.Image):
        x = preprocess_onnx(patch, size=224)
        logits = self.sess.run([self.output_name], {self.input_name: x})[0]
        # softmax on logits
        e = np.exp(logits - logits.max(axis=1, keepdims=True))
        proba = e / e.sum(axis=1, keepdims=True)
        return proba[0]
