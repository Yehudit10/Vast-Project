# Purpose: Unit tests for the DiseaseDetector class.
# Ensures the model loads successfully and returns valid detections on dummy input.

import pytest
from agri_baseline.src.detectors.disease_model import DiseaseDetector
import numpy as np

def test_disease_detector_model_loads():
    detector = DiseaseDetector(model_path="models/cnn_multi_stage3.pth")
    assert detector.model is not None, "Model failed to load correctly."

def test_disease_detector_predicts():
    detector = DiseaseDetector()
    img = np.zeros((224, 224, 3))  # Dummy image for testing
    detections = detector.run(img)
    assert len(detections) > 0, "Model did not return any detections."
    assert detections[0].confidence > 0, "Detection confidence should be greater than 0."
