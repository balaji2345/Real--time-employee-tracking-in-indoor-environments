import cv2
from ultralytics import YOLO
import supervision as sv
import os

# ── Config ──────────────────────────────────────
MODEL_PATH  = 'runs/detect/workforce_monitor/staff_customer_v4/weights/best.pt'
IMAGE_PATH  = 'test_image.png'
OUTPUT_PATH = 'output/test_output.jpg'
CONF        = 0.25

os.makedirs("output", exist_ok=True)

# Load model
model = YOLO(MODEL_PATH)

def format_time(seconds):
    seconds = int(max(0, seconds))
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"

def draw_label_box(frame, text, x1, y1, color):
    font       = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.52
    thickness  = 1
    (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)

    cv2.rectangle(frame,
                  (x1, y1 - th - 8),
                  (x1 + tw + 6, y1),
                  color, -1)

    cv2.putText(frame,
                text,
                (x1 + 3, y1 - 4),
                font,
                font_scale,
                (255,255,255),
                thickness)

# ── Load Image ──────────────────────────────────
frame = cv2.imread(IMAGE_PATH)

if frame is None:
    print("Error: Image not found")
    exit()

# ── Run Detection ───────────────────────────────
results = model(frame, conf=CONF, verbose=False)[0]
detections = sv.Detections.from_ultralytics(results)

staff_count = 0
customer_count = 0

for i in range(len(detections)):
    
    xyxy = detections.xyxy[i]
    cls_id = int(detections.class_id[i])
    label = model.names[cls_id]

    x1, y1, x2, y2 = map(int, xyxy)

    # Colors
    if label == 'Staff':
        color = (0,200,0)
        staff_count += 1
    else:
        color = (0,140,255)
        customer_count += 1

    # Bounding box
    cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)

    # Label
    draw_label_box(frame,
                   f"{label}",
                   x1,y1,
                   color)

# ── HUD ─────────────────────────────────────────
cv2.rectangle(frame,(0,0),(220,70),(0,0,0),-1)

cv2.putText(frame,
            f"Staff : {staff_count}",
            (10,26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,(0,200,0),2)

cv2.putText(frame,
            f"Customer : {customer_count}",
            (10,54),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,(0,140,255),2)

# ── Save Result ─────────────────────────────────
cv2.imwrite(OUTPUT_PATH, frame)

# ── Display Result ──────────────────────────────
cv2.imshow("Image Test", frame)
cv2.waitKey(0)
cv2.destroyAllWindows()

print("Detection finished")
print(f"Saved output to: {OUTPUT_PATH}")