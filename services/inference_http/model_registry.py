from adapters.fruit_defect_runner import FruitDefectRunner
from adapters.fruit_segmentation_runner import FruitSegmentationRunner

def get_model_runner(team: str):
    t = (team or "").lower()
    if t == "fruit_defect":
        return FruitDefectRunner()
    if t == "camera":                      
        return FruitSegmentationRunner()
    raise ValueError(f"unknown TEAM {t}")
