from heuristics import Features

# bitmask:
LOW_LIGHT      = 1     
BLURRY         = 2     
SMALL_MASK     = 4     
NEAR_THRESHOLD = 8     
OUTLIER        = 16
GREEN_LEAF_BIT = 32    

def near_threshold(f: Features, thr: dict) -> bool:
    close_brown = abs(f.brown_ratio - thr["overripe_brown_ratio"]) < thr["near_brown_delta"]
    close_hue   = (thr["unripe_h_min"] <= f.mean_h <= thr["unripe_h_min"]+5) or \
                  (thr["unripe_h_max"]-5 <= f.mean_h <= thr["unripe_h_max"])
    return close_brown or close_hue

def quality_flags(f: Features, thr: dict, leaf_ratio: float, mark_outlier: bool=False) -> int:
    
    flags = 0
    if f.mean_v < thr["low_light_v"]:
        flags |= LOW_LIGHT
    if f.lap_var < thr["blurry_lap_var"]:
        flags |= BLURRY
    if f.mask_cov < thr["small_mask_cov"]:
        flags |= SMALL_MASK
    if near_threshold(f, thr):
        flags |= NEAR_THRESHOLD

    gl_thr = thr.get("green_leaf_ratio_thr", 0.10)  
    if leaf_ratio > gl_thr:
        flags |= GREEN_LEAF_BIT

    if mark_outlier:
        flags |= OUTLIER
    return flags
