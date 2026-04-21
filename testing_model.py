from ultralytics import YOLO
import cv2
import os

# Load your trained model
model = YOLO('runs/detect/workforce_monitor/staff_customer_v2/weights/best.pt')

# Run on test images from dataset
test_img_dir = r'C:\Users\TIH48\Desktop\workforce_monitor\frames'
output_dir   = 'test_results2'
os.makedirs(output_dir, exist_ok=True)

images = os.listdir(test_img_dir)[:8863]  # test on first 5 images

for img_name in images:
    img_path = os.path.join(test_img_dir, img_name)
    img      = cv2.imread(img_path)

    results  = model(img, conf=0.5)[0]

    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cls    = int(box.cls[0])
        conf   = float(box.conf[0])
        label  = model.names[cls]

        # Green for Staff, Orange for Customer
        color  = (0, 200, 0) if label == 'Staff' else (0, 140, 255)

        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.putText(img, f"{label} {conf:.2f}",
                    (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, color, 2)

    out_path = os.path.join(output_dir, img_name)
    cv2.imwrite(out_path, img)
    print(f"Saved: {out_path}")

print("=" * 45)
print(f"Results saved to: {output_dir}/")
print("Open the folder to see detections.")