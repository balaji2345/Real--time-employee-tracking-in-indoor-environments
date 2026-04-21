import os
import shutil
import yaml

dataset1 = "StaffIdentify-3"       # original 1113 images
dataset2 = "workforce-monitor-3"   # fully annotated restaurant 347 images

merged = "dataset_merged_v2"

for split in ["train", "valid", "test"]:
    os.makedirs(f"{merged}/{split}/images", exist_ok=True)
    os.makedirs(f"{merged}/{split}/labels", exist_ok=True)

print("=" * 45)
print("MERGING DATASETS v2")
print("=" * 45)

def copy_files(src_dataset, split, count_start=0):
    img_src = os.path.join(src_dataset, split, "images")
    lbl_src = os.path.join(src_dataset, split, "labels")

    if not os.path.exists(img_src):
        split_alt = "valid" if split == "val" else "val"
        img_src = os.path.join(src_dataset, split_alt, "images")
        lbl_src = os.path.join(src_dataset, split_alt, "labels")

    if not os.path.exists(img_src):
        print(f"  Skipping {src_dataset}/{split} - not found")
        return 0

    img_dst = f"{merged}/{split}/images"
    lbl_dst = f"{merged}/{split}/labels"

    copied = 0
    for fname in os.listdir(img_src):
        if not fname.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue

        base = os.path.splitext(fname)[0]
        ext  = os.path.splitext(fname)[1]

        new_name = f"{src_dataset}_{count_start+copied}"
        src_img  = os.path.join(img_src, fname)
        src_lbl  = os.path.join(lbl_src, base + ".txt")
        dst_img  = os.path.join(img_dst, new_name + ext)
        dst_lbl  = os.path.join(lbl_dst, new_name + ".txt")

        shutil.copy2(src_img, dst_img)
        if os.path.exists(src_lbl):
            shutil.copy2(src_lbl, dst_lbl)

        copied += 1

    return copied

for split in ["train", "valid", "test"]:
    c1 = copy_files(dataset1, split, count_start=0)
    c2 = copy_files(dataset2, split, count_start=c1)
    print(f"{split:<6} → {c1} from StaffIdentify + {c2} from restaurant = {c1+c2} total")

merged_yaml = {
    "path": os.path.abspath(merged),
    "train": "train/images",
    "val":   "valid/images",
    "test":  "test/images",
    "nc":    2,
    "names": ["Customer", "Staff"]
}

with open(f"{merged}/data.yaml", "w") as f:
    yaml.dump(merged_yaml, f, default_flow_style=False)

print("\n" + "=" * 45)
print("MERGE COMPLETE")
print("=" * 45)
print(f"Output folder : {merged}/")
print(f"Classes       : {merged_yaml['names']}")

for split in ["train", "valid", "test"]:
    count = len(os.listdir(f"{merged}/{split}/images"))
    print(f"{split:<6} images : {count}")