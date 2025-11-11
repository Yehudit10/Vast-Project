# Purpose: Tests for running the DiseaseDetector model.
# Checks that detections are produced with valid confidence values on dummy images.

import pytest
from agri_baseline.src.detectors.disease_model import DiseaseDetector
import numpy as np

@pytest.fixture
def dummy_image():
    """Provide a dummy image for testing."""
    return np.zeros((224, 224, 3))  # Black dummy image

def test_disease_detector_runs(dummy_image):
    detector = DiseaseDetector()
    detections = detector.run(dummy_image)
    assert len(detections) > 0, "Disease detection did not return any detections."
    assert detections[0].confidence > 0, "Detection confidence should be greater than 0."

def test_disease_detector_model_loads():
    detector = DiseaseDetector(model_path="models/cnn_multi_stage3.pth")
    assert detector.model is not None, "Model failed to load correctly."
