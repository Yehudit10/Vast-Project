from fastapi import FastAPI, UploadFile, File
from fastapi.responses import Response, JSONResponse
import torch, torch.nn.functional as F
import cv2, numpy as np, tempfile, math
from transformers import SegformerForSemanticSegmentation, SegformerConfig
from oem_palette import NUM_CLASSES, PALETTE
from scipy import ndimage
import json
import logging
import os

logger = logging.getLogger("segformer_api")
logger.setLevel(logging.INFO)  
formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
if not logger.hasHandlers():
    logger.addHandler(console_handler)

logger.propagate = False

# =========================================================
# ⚙️ General Settings
# =========================================================
app = FastAPI(title="🛰️ SegFormer-B3 Smart Inference API (Enhanced Road Logic)")

@app.get("/health")
def health():
    return {"status": "ok"}

MODEL_PATH = "model/segmentation_api.pth"
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
logger.info(f"✅ Using device: {device}")

# =========================================================
# 🧠 Model Loading
# =========================================================
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"❌ Model not found at: {MODEL_PATH}")

config = SegformerConfig(
    backbone="mit_b3",
    num_labels=NUM_CLASSES,
    hidden_sizes=[64, 128, 320, 512],
    depths=[3, 4, 18, 3],
    decoder_hidden_size=768,
    ignore_mismatched_sizes=True
)
model = SegformerForSemanticSegmentation(config)
state_dict = torch.load(MODEL_PATH, map_location=device)
model.load_state_dict(state_dict, strict=False)
model.to(device).eval()
logger.info("✅ SegFormer-B3 model loaded successfully!")


# =========================================================
# 🎨 Helper Functions
# =========================================================
def preprocess_image(img: np.ndarray):
    img = cv2.resize(img, (512, 512))
    img = img.astype(np.float32) / 255.0
    img = img.transpose(2, 0, 1)
    return torch.from_numpy(img).unsqueeze(0).to(device)


def predict_probs(img: np.ndarray):
    inputs = preprocess_image(img)
    with torch.no_grad():
        outputs = model(pixel_values=inputs)
        logits = outputs.logits
        logits = F.interpolate(logits, size=img.shape[:2], mode="bilinear", align_corners=False)
        probs = torch.softmax(logits, dim=1)[0].cpu().numpy()
    return probs


def compute_class_distribution(mask):
    h, w = mask.shape
    total = h * w
    counts = {}
    index_to_name = {v[0]: v[1] for v in PALETTE.values()}
    for cls_idx, cls_name in index_to_name.items():
        cls_pixels = np.sum(mask == cls_idx)
        percent = round(100 * cls_pixels / total, 2)
        if percent > 0:
            counts[cls_name] = percent
    return counts


def colorize_mask(mask):
    color_mask = np.zeros((mask.shape[0], mask.shape[1], 3), dtype=np.uint8)
    for color, (cls_idx, _) in PALETTE.items():
        color_mask[mask == cls_idx] = color
    return color_mask


def refine_water_only(mask, probs, water_conf_thresh=0.8):
    refined_mask = mask.copy()
    top2 = np.argsort(-probs, axis=2)
    second_best = top2[:, :, 1]
    best_conf = np.max(probs, axis=2)

    WATER_CLASS = next((v[0] for k, v in PALETTE.items() if v[1].lower() == "water"), None)
    if WATER_CLASS is not None:
        low_conf_water = (mask == WATER_CLASS) & (best_conf < water_conf_thresh)
        refined_mask[low_conf_water] = second_best[low_conf_water]
        logger.info(f"💧 Replaced {np.sum(low_conf_water)} low-confidence water pixels")

    return refined_mask


def remove_small_roads(mask, probs, min_road_area=600, debug_visualize=True):
    refined_mask = mask.copy()
    ROAD_CLASS = next((v[0] for k, v in PALETTE.items() if v[1].lower() == "road"), None)
    if ROAD_CLASS is None:
        logger.warning("⚠️ ROAD_CLASS not found in PALETTE")
        return refined_mask

    road_mask = (refined_mask == ROAD_CLASS).astype(np.uint8)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(road_mask, connectivity=8)

    logger.info(f"🛣️ Found {num_labels - 1} road regions (min_road_area={min_road_area})")

    if debug_visualize:
        color_debug = colorize_mask(mask).copy()

    removed = 0
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        x, y = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
        w, h = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        cx, cy = centroids[i]
        region_mask = (labels == i)

        logger.info(f"🚗 Road #{i:02d} | area={area:7.1f}px | bbox=({x},{y},{w},{h})")

        color = (0, 255, 0) if area >= min_road_area else (0, 0, 255)
        if debug_visualize:
            cv2.rectangle(color_debug, (x, y), (x + w, y + h), color, 2)
            cv2.putText(color_debug, f"{i}", (x + 5, y + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

        if area < min_road_area:
            dilated = ndimage.binary_dilation(region_mask, iterations=10)
            neighbors = refined_mask[dilated & (~region_mask)]

            if len(neighbors) > 0:
                dominant_class = np.bincount(neighbors).argmax()
            else:
                dominant_class = 0 

            refined_mask[region_mask] = dominant_class
            logger.info(f"   🧭 Replaced with surrounding class: {dominant_class}")
            removed += 1

    logger.info(f"✅ Finished checking all roads — removed {removed}/{num_labels - 1}")

    return refined_mask

def connect_roads_perfect(
    color_mask,
    road_color=(255, 255, 255),
    max_distance=200,
    angle_threshold=35,
    connection_angle_limit=45,
    line_thickness=6,
    min_area=50,
    connect_extend=15,
    debug=True
):
    tolerance = 20
    low = np.array([max(0, c - tolerance) for c in road_color])
    high = np.array([min(255, c + tolerance) for c in road_color])
    road_mask = cv2.inRange(color_mask, low, high)

    kernel = np.ones((5, 5), np.uint8)
    road_mask = cv2.morphologyEx(road_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(road_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    connected_mask = color_mask.copy()
    directions = []

    if debug:
        logger.info(f"✅ Found {len(contours)} road segments")

    for idx, cnt in enumerate(contours):
        area = cv2.contourArea(cnt)
        if area < min_area:
            directions.append(None)
            continue

        data_pts = np.array(cnt[:, 0, :], dtype=np.float64)
        _, eigenvectors = cv2.PCACompute(data_pts, mean=np.array([]))
        vx, vy = eigenvectors[0]
        angle = math.degrees(math.atan2(vy, vx))
        directions.append((vx, vy, angle))
        if debug:
            logger.info(f"  🟡 Segment {idx}: area={area:.1f}, angle={angle:.1f}°")

    connections = 0

    for i in range(len(contours)):
        if directions[i] is None:
            continue
        for j in range(i + 1, len(contours)):
            if directions[j] is None:
                continue

            cnt1, cnt2 = contours[i], contours[j]
            min_dist = 1e9
            pt1_min, pt2_min = None, None

            for p1 in cnt1:
                for p2 in cnt2:
                    d = np.linalg.norm(p1[0] - p2[0])
                    if d < min_dist:
                        min_dist = d
                        pt1_min, pt2_min = tuple(p1[0]), tuple(p2[0])

            if min_dist > max_distance:
                continue

            (vx1, vy1, angle1) = directions[i]
            (vx2, vy2, angle2) = directions[j]
            avg_angle = (angle1 + angle2) / 2
            diff_angle = abs(angle1 - angle2)
            diff_angle = min(diff_angle, 180 - diff_angle)
            
            dx, dy = pt2_min[0] - pt1_min[0], pt2_min[1] - pt1_min[1]
            length = math.hypot(dx, dy)
            if length == 0:
                continue
            ux, uy = dx / length, dy / length
            connection_angle = math.degrees(math.atan2(uy, ux))

            def angle_between(vx, vy, ux, uy):
                dot = vx * ux + vy * uy
                cross = vx * uy - vy * ux
                ang = abs(math.degrees(math.atan2(cross, dot)))
                return min(ang, 180 - ang)

            ang_to_road1 = angle_between(vx1, vy1, ux, uy)
            ang_to_road2 = angle_between(vx2, vy2, ux, uy)

            if debug:
                logger.info(f"🔹 {i}↔{j} | dist={min_dist:.1f}px | Δdir={diff_angle:.1f}° | "
                      f"Δconn1={ang_to_road1:.1f}° | Δconn2={ang_to_road2:.1f}°")

            if (
                diff_angle < angle_threshold and
                ang_to_road1 < connection_angle_limit and
                ang_to_road2 < connection_angle_limit
            ):
                p1, p2 = np.array(pt1_min, np.float32), np.array(pt2_min, np.float32)
                p1_ext = (p1 - np.array([ux, uy]) * connect_extend).astype(int)
                p2_ext = (p2 + np.array([ux, uy]) * connect_extend).astype(int)

                cv2.line(connected_mask, tuple(p1_ext), tuple(p2_ext),
                         road_color, line_thickness, lineType=cv2.LINE_8)
                connections += 1
                if debug:
                    logger.info(f"  ✅ Connected {i}↔{j}")

    if debug:
        logger.info(f"✅ Total valid connections: {connections}")
        if connections == 0:
            print("⚠️ No connections made — try increasing max_distance slightly.")

    return connected_mask


def apply_confidence_threshold(probs, mask, threshold=0.6):
    best_conf = np.max(probs, axis=2)
    low_conf_mask = best_conf < threshold
    mask[low_conf_mask] = 0  
    logger.info(f"⚙️ Converted {np.sum(low_conf_mask)} low-confidence pixels to class 0 (Other)")
    return mask


@app.post("/infer")
async def infer_image(file: UploadFile = File(...), threshold: float = 0.3):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        img = cv2.cvtColor(cv2.imread(tmp_path), cv2.COLOR_BGR2RGB)
        os.remove(tmp_path) 
        probs = predict_probs(img)
        mask = np.argmax(probs, axis=0)
        probs = np.transpose(probs, (1, 2, 0))
        mask = apply_confidence_threshold(probs, mask, threshold=threshold)


        mask = refine_water_only(mask, probs, water_conf_thresh=1)

        color_mask = colorize_mask(mask)

        logger.info("🚗 Connecting roads before removing small ones...")
        connected_color = connect_roads_perfect(
            color_mask,
            max_distance=120,
            angle_threshold=35,
            debug=True
        )

        connected_mask = np.zeros(mask.shape, dtype=np.uint8)

        for color, (cls_idx, _) in PALETTE.items():
            lower = np.clip(np.array(color) - 20, 0, 255).astype(np.uint8)
            upper = np.clip(np.array(color) + 20, 0, 255).astype(np.uint8)
            mask_area = cv2.inRange(connected_color, lower, upper)
            connected_mask[mask_area > 0] = cls_idx

        logger.info(f"🖼️ mask shape: {mask.shape}, unique values: {np.unique(mask)}")
        logger.info(f"🖼️ connected_mask shape: {connected_mask.shape}, unique values: {np.unique(connected_mask)}")
        logger.info("🚗 sending to remove_small_roads() ...")

        refined_mask = remove_small_roads(connected_mask, probs, min_road_area=1000)

        final_color_mask = colorize_mask(refined_mask)
        dist = compute_class_distribution(refined_mask)

        _, buffer = cv2.imencode(".png", cv2.cvtColor(final_color_mask, cv2.COLOR_RGB2BGR))
        return Response(content=buffer.tobytes(), media_type="image/png",
                        headers={"X-Class-Distribution": json.dumps(dist)})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

