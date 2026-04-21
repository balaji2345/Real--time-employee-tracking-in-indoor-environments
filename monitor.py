import cv2
import time
from ultralytics import YOLO
import supervision as sv
from datetime import datetime
import os

# ── Config 
MODEL_PATH  = 'runs/detect/workforce_monitor/staff_customer_v4/weights/best.pt'
VIDEO_PATH  = 'video1.mp4'
OUTPUT_PATH = 'output/monitored_output.mp4'
CAMERA_ID   = 'Camera 1'
CONF        = 0.35

IDLE_MOVE_THRESHOLD = 15
IDLE_CONFIRM_SECS   = 3


os.makedirs("output", exist_ok=True)

model   = YOLO(MODEL_PATH)
tracker = sv.ByteTrack()

track_data = {}

def format_time(seconds):
    seconds = int(max(0, seconds))
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"

def get_center(xyxy):
    x1, y1, x2, y2 = xyxy
    return int((x1 + x2) / 2), int((y1 + y2) / 2)

def draw_label_box(frame, text, x1, y1, color):
    font       = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.52
    thickness  = 1
    (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
    cv2.rectangle(frame,
                  (x1, y1 - th - 8),
                  (x1 + tw + 6, y1),
                  color, -1)
    cv2.putText(frame, text,
                (x1 + 3, y1 - 4),
                font, font_scale,
                (255, 255, 255), thickness)

# ── Video setup ──────────────────────────────────
cap    = cv2.VideoCapture(VIDEO_PATH)
width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps    = cap.get(cv2.CAP_PROP_FPS)
total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

out = cv2.VideoWriter(
    OUTPUT_PATH,
    cv2.VideoWriter_fourcc(*'mp4v'),
    fps,
    (width, height)
)

print("=" * 50)
print("WORKFORCE & QUEUE MONITOR")
print("=" * 50)
print(f"Video   : {VIDEO_PATH}")
print(f"Output  : {OUTPUT_PATH}")
print(f"Size    : {width}x{height}  FPS: {fps:.1f}")
print(f"Press Q to quit early")
print("=" * 50)

frame_count = 0

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # Current video time in seconds
    video_time = frame_count / fps

    results    = model(frame, conf=CONF, verbose=False)[0]
    detections = sv.Detections.from_ultralytics(results)

    if len(detections) > 0:
        detections = tracker.update_with_detections(detections)

    staff_count    = 0
    customer_count = 0

    for i in range(len(detections)):
        xyxy       = detections.xyxy[i]
        cls_id     = int(detections.class_id[i])
        tracker_id = int(detections.tracker_id[i])
        label      = model.names[cls_id]

        x1, y1, x2, y2 = map(int, xyxy)
        cx, cy = get_center((x1, y1, x2, y2))

        # ── Init tracker data ─────────────────────
        if tracker_id not in track_data:
            track_data[tracker_id] = {
                'class'       : label,
                'first_seen'  : video_time,
                'last_seen'   : video_time,
                'last_pos'    : (cx, cy),
                'idle_since'  : video_time,
                'idle_time'   : 0,
                'active_time' : 0,
                'is_idle'     : False,
            }

        td = track_data[tracker_id]
        td['last_seen'] = video_time
        td['class']     = label

        # ── Movement check (Staff only) ───────────
        if label == 'Staff':
            lx, ly = td['last_pos']
            moved  = ((cx - lx) ** 2 + (cy - ly) ** 2) ** 0.5

            if moved > IDLE_MOVE_THRESHOLD:
                if td['is_idle']:
                    td['idle_time'] += video_time - td['idle_since']
                td['is_idle']    = False
                td['idle_since'] = video_time
                td['last_pos']   = (cx, cy)
            else:
                if not td['is_idle']:
                    idle_pending = video_time - td['idle_since']
                    if idle_pending > IDLE_CONFIRM_SECS:
                        td['is_idle']   = True
                        td['idle_since'] = video_time
                else:
                    td['idle_time'] = video_time - td['idle_since']

            active_secs = max(0, video_time - td['first_seen'] - td['idle_time'])
            idle_secs   = td['idle_time']

        # ── Wait time per customer ─────────────────
        wait_secs = video_time - td['first_seen']

        # ── Colors ────────────────────────────────
        if label == 'Staff':
            color = (0, 180, 255) if td['is_idle'] else (0, 200, 0)
            staff_count += 1
        else:
            color = (0, 140, 255)
            customer_count += 1

        # ── Draw bounding box ─────────────────────
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        # ── Draw labels ───────────────────────────
        if label == 'Staff':
            draw_label_box(frame,
                           f"Idle   : {format_time(idle_secs)}",
                           x1, y1 - 44, (80, 80, 80))
            draw_label_box(frame,
                           f"Active : {format_time(active_secs)}",
                           x1, y1 - 24, (80, 80, 80))
            draw_label_box(frame,
                           f"STAFF  id:{tracker_id}",
                           x1, y1, color)
        else:
            draw_label_box(frame,
                           f"Wait: {format_time(wait_secs)}",
                           x1, y1 - 22, (80, 80, 80))
            draw_label_box(frame,
                           f"CUSTOMER  id:{tracker_id}",
                           x1, y1, color)

    # ── HUD — top left ────────────────────────────
    cv2.rectangle(frame, (0, 0), (230, 70), (0, 0, 0), -1)
    cv2.putText(frame, f"Staff    : {staff_count}",
                (10, 26), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (0, 200, 0), 2)
    cv2.putText(frame, f"Customer : {customer_count}",
                (10, 54), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (0, 140, 255), 2)

    # ── Timestamp + Camera ID ─────────────────────
    ts = datetime.now().strftime("%d-%m-%Y %a %H:%M:%S")
    cv2.putText(frame, ts,
                (10, height - 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6, (255, 255, 255), 1)
    cv2.putText(frame, CAMERA_ID,
                (width - 120, height - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6, (255, 255, 255), 1)

    # ── Write + Display ───────────────────────────
    out.write(frame)
    cv2.imshow("Workforce Monitor", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("Quit early by user.")
        break

    frame_count += 1
    if frame_count % 200 == 0:
        pct = round((frame_count / total) * 100)
        print(f"Progress: {frame_count}/{total} frames ({pct}%)")

cap.release()
out.release()
cv2.destroyAllWindows()

print("=" * 50)
print(f"Done. {frame_count} frames processed.")
print(f"Saved to: {OUTPUT_PATH}")
print("=" * 50)