import os
from collections import Counter

label_dir = "dataset_merged_v2/train/labels"
class_counts = Counter()
problem_files = []

for fname in os.listdir(label_dir):
    if not fname.endswith(".txt"):
        continue
    fpath = os.path.join(label_dir, fname)
    with open(fpath, "r") as f:
        lines = f.readlines()
    for line in lines:
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        cls_id = int(parts[0])
        class_counts[cls_id] += 1
        if cls_id > 1:
            problem_files.append((fname, cls_id))

print("=" * 45)
print("LABEL CLASS DISTRIBUTION")
print("=" * 45)
print(f"Class 0 (Customer) : {class_counts[0]} instances")
print(f"Class 1 (Staff)    : {class_counts[1]} instances")

if class_counts:
    ratio = class_counts[0] / max(class_counts[1], 1)
    print(f"Imbalance ratio    : {ratio:.1f}:1")

if problem_files:
    print(f"\nWARNING: {len(problem_files)} labels with class ID > 1 found")
    for f, c in problem_files[:5]:
        print(f"  {f} → class {c}")
    print("These need to be fixed before training.")
else:
    print("\n✓ All class IDs are 0 or 1 — no issues found")

print("=" * 45)