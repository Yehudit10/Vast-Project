from adapters.fruit_defect_runner import FruitDefectRunner
from adapters.fruit_segmentation_runner import FruitSegmentationRunner
from adapters.soil_moisture_runner import SoilMoistureRunner
from adapters.rover_runner import RoverRunner


def get_model_runner(team: str):
    t = (team or "").lower()
    if t == "fruit_defect":
        return FruitDefectRunner()
    if t == "camera":                      
        return FruitSegmentationRunner()
    if t == "soil_moisture":
        return SoilMoistureRunner()
    if t == "rover":
        return RoverRunner()
    raise ValueError(f"unknown TEAM {t}")
