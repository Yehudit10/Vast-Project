# labels_map.py
# Bucketing tags into 4 coarse groups using keyword matching.

ANIMAL_KEYWORDS = [
    "Animal", "Dog", "Cat", "Bird", "Insect", "Roar", "Meow", "Bark", "Chirp",
    "Cow", "Sheep", "Horse", "Pig", "Duck", "Frog", "Goat", "Rooster", "Owl",
    "Bee", "Mosquito", "Chicken"
]

VEHICLE_KEYWORDS = [
    "Vehicle", "Car", "Automobile", "Truck", "Bus", "Motorcycle", "Aircraft",
    "Airplane", "Helicopter", "Boat", "Ship", "Engine", "Train", "Rail",
    "Subway", "Tram", "Bicycle", "Siren"
]

SHOTGUN_KEYWORDS = [
    "Gunshot", "Gunfire", "Firearm", "Shotgun", "Rifle", "Pistol", "Machine gun", "Cap gun"
]


def bucket_of(label: str) -> str:
    """
    Return one of: {"animal", "vehicle", "shotgun", "other"} based on simple keyword checks.
    """
    l = label.lower()
    if any(k.lower() in l for k in SHOTGUN_KEYWORDS):
        return "shotgun"
    if any(k.lower() in l for k in VEHICLE_KEYWORDS):
        return "vehicle"
    if any(k.lower() in l for k in ANIMAL_KEYWORDS):
        return "animal"
    return "other"
