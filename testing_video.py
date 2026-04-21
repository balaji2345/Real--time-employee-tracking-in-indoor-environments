from ultralytics import YOLO
import cv2
import os

model = YOLO('runs/detect/workforce_monitor/staff_customer_v4/weights/best.pt')

# Use one of your restaurant videos
video_path = "video.mp4"
output_path = "test_results_v4/output_video.mp4"

os.makedirs("test_results_v4", exist_ok=True)

cap = cv2.VideoCapture(video_path)
width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps    = cap.get(cv2.CAP_PROP_FPS)
total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

out = cv2.VideoWriter(
    output_path,
    cv2.VideoWriter_fourcc(*'mp4v'),
    fps,
    (width, height)
)

print("=" * 45)
print("RUNNING MODEL ON VIDEO")
print("=" * 45)
print(f"Input  : {video_path}")
print(f"Size   : {width}x{height}")
print(f"FPS    : {fps:.1f}")
print(f"Frames : {total}")
print("Processing...")

frame_count = 0

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    results = model(frame, conf=0.35, verbose=False)[0]

    staff_count    = 0
    customer_count = 0

    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cls   = int(box.cls[0])
        conf  = float(box.conf[0])
        label = model.names[cls]

        # Green for Staff, Orange for Customer
        color = (0, 200, 0) if label == 'Staff' else (0, 140, 255)

        # Draw box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        # Draw label background
        label_text = f"{label} {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label_text,
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(frame,
                      (x1, y1 - th - 10),
                      (x1 + tw + 4, y1),
                      color, -1)
        cv2.putText(frame, label_text,
                    (x1 + 2, y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (255, 255, 255), 2)

        if label == 'Staff':
            staff_count += 1
        else:
            customer_count += 1

    # HUD overlay — top left counter
    cv2.rectangle(frame, (0, 0), (220, 65), (0, 0, 0), -1)
    cv2.putText(frame, f"Staff    : {staff_count}",
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 0), 2)
    cv2.putText(frame, f"Customer : {customer_count}",
                (10, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 140, 255), 2)

    out.write(frame)
    frame_count += 1

    if frame_count % 100 == 0:
        pct = round((frame_count / total) * 100)
        print(f"  Progress: {frame_count}/{total} frames ({pct}%)")

cap.release()
out.release()

print("=" * 45)
print(f"Done. {frame_count} frames processed.")
print(f"Output saved to: {output_path}")
print("Open test_results_v2/output_video.mp4 to review.")
print("=" * 45)