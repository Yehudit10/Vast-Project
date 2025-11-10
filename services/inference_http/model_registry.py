# from typing import Any, Dict
# from adapters.fruit_defect_runner import FruitDefectRunner

# class FruitRunner:
#     def __init__(self):
#         self.impl = FruitDefectRunner()

#     def run(self, image_bytes: bytes, model_tag=None, extra=None) -> Dict[str, Any]:
#         return self.impl.run(image_bytes, model_tag=model_tag, extra=extra)

# def get_model_runner(team: str):
#     t = (team or "").lower()
#     if t == "fruit":
#         return FruitRunner()
#     raise ValueError(f"unknown TEAM {t}")


from adapters.fruit_defect_runner import FruitDefectRunner
from adapters.fruit_segmentation_runner import FruitSegmentationRunner

def get_model_runner(team: str):
    t = (team or "").lower()
    if t == "fruit_defect":
        return FruitDefectRunner()
    if t == "camera":                      
        return FruitSegmentationRunner()
    raise ValueError(f"unknown TEAM {t}")
