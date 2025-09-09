from .heuristics import Features

# bitmask:
LOW_LIGHT      = 1     # mean_v < low_light_v
BLURRY         = 2     # lap_var < blurry_lap_var
SMALL_MASK     = 4     # mask_cov < small_mask_cov
NEAR_THRESHOLD = 8     # קרוב לספי החלטה
OUTLIER        = 16    # שמור לשלב ב'; כרגע 0 כברירת מחדל

def near_threshold(f: Features, thr: dict) -> bool:
    # קרבה לסף brown_ratio או לגבולות ה-Hue הלא-בשלים
    close_brown = abs(f.brown_ratio - thr["overripe_brown_ratio"]) < thr["near_brown_delta"]
    close_hue   = (thr["unripe_h_min"] <= f.mean_h <= thr["unripe_h_min"]+5) or \
                  (thr["unripe_h_max"]-5 <= f.mean_h <= thr["unripe_h_max"])
    return close_brown or close_hue

def quality_flags(f: Features, thr: dict, mark_outlier: bool=False) -> int:
    flags = 0
    if f.mean_v < thr["low_light_v"]:
        flags |= LOW_LIGHT
    if f.lap_var < thr["blurry_lap_var"]:
        flags |= BLURRY
    if f.mask_cov < thr["small_mask_cov"]:
        flags |= SMALL_MASK
    if near_threshold(f, thr):
        flags |= NEAR_THRESHOLD
    if mark_outlier:
        flags |= OUTLIER
    return flags
