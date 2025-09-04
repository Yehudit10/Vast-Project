# labels_map.py
# נשתמש בהתאמה ע"י מילות מפתח בשמות התגים של AudioSet
ANIMAL_KEYWORDS = [
    "Animal", "Dog", "Cat", "Bird", "Insect", "Roar", "Meow", "Bark", "Chirp",
    "Cow", "Sheep", "Horse", "Pig", "Duck", "Frog", "Goat", "Rooster"
]

VEHICLE_KEYWORDS = [
    "Vehicle", "Car", "Automobile", "Truck", "Bus", "Motorcycle", "Aircraft",
    "Airplane", "Helicopter", "Boat", "Ship", "Engine", "Train", "Rail", "Subway"
]

SHOTGUN_KEYWORDS = [
    "Gunshot", "Gunfire", "Firearm", "Shotgun", "Rifle", "Pistol", "Machine gun"
]

def bucket_of(label: str) -> str:
    l = label.lower()
    if any(k.lower() in l for k in SHOTGUN_KEYWORDS):
        return "shotgun"
    if any(k.lower() in l for k in VEHICLE_KEYWORDS):
        return "vehicle"
    if any(k.lower() in l for k in ANIMAL_KEYWORDS):
        return "animal"
    return "other"
