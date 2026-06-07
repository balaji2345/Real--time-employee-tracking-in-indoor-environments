from ultralytics import YOLO

def main():
    model = YOLO('yolov8m.pt')  # fresh pretrained base

    results = model.train(
        data='dataset_merged_v2/data.yaml',
        epochs=50,
        imgsz=1200,
        batch=8,
        device=0,
        workers=2,
        patience=15,
        augment=True,
        cos_lr=True,
        optimizer='AdamW',
        lr0=0.001,
        weight_decay=0.0005,
        cls=4.0,
        project='workforce_monitor',
        name='staff_customer_v4',
        exist_ok=True,
        verbose=True
    )

    print("=" * 45)
    print("TRAINING COMPLETE")
    print("=" * 45)
    print(f"Best model : {results.save_dir}/weights/best.pt")
    print(f"mAP50      : {results.results_dict.get('metrics/mAP50(B)', 'N/A')}")
    print(f"mAP50-95   : {results.results_dict.get('metrics/mAP50-95(B)', 'N/A')}")

if __name__ == '__main__':
    main()
