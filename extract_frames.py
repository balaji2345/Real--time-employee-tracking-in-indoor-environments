import cv2
import os

def is_blurry(frame, threshold=100):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var() < threshold

def is_dark(frame, threshold=40):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return gray.mean() < threshold

def extract_smart(video_path, output_dir, sample_every=30, max_frames=300):
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"ERROR: Cannot open {video_path}")
        return 0

    total     = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps       = cap.get(cv2.CAP_PROP_FPS)
    duration  = total / fps / 60

    print(f"\nVideo    : {os.path.basename(video_path)}")
    print(f"Frames   : {total}")
    print(f"FPS      : {fps:.1f}")
    print(f"Duration : {duration:.1f} minutes")

    saved = 0
    count = 0
    skipped_blur = 0
    skipped_dark = 0

    while cap.isOpened() and saved < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if count % sample_every == 0:
            if is_blurry(frame):
                skipped_blur += 1
            elif is_dark(frame):
                skipped_dark += 1
            else:
                name = f"{os.path.basename(video_path).split('.')[0]}_frame_{count:06d}.jpg"
                cv2.imwrite(os.path.join(output_dir, name), frame, 
                           [cv2.IMWRITE_JPEG_QUALITY, 95])
                saved += 1

        count += 1

    cap.release()

    print(f"Saved    : {saved} frames")
    print(f"Skipped  : {skipped_blur} blurry, {skipped_dark} dark")
    return saved

if __name__ == '__main__':
    videos = [
        "video.mp4",
    ]

    output_dir = "unseen_frames"
    total_saved = 0

    print("=" * 45)
    print("SMART FRAME EXTRACTION")
    print("=" * 45)

    for video in videos:
        saved = extract_smart(
            video_path=video,
            output_dir=output_dir,
            sample_every=30,    # 1 frame every 30 frames
            max_frames=200      # max 300 frames per video
        )
        total_saved += saved

    print("\n" + "=" * 45)
    print(f"Total frames saved : {total_saved}")
    print(f"Output folder      : {output_dir}/")
    print("Ready for annotation.")
    print("=" * 45)