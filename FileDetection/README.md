# FileDetection

ML-powered file screening pipeline used by SyncDose's backup feature. When the Android app
sends files during a backup session, `BackupService` runs each file through this pipeline to
detect exact duplicates, corrupted files, and unwanted images before saving them to disk.

---

## Modules

### `detector.py` — Corruption Detection

```python
from detector import is_corrupt

if is_corrupt(Path("photo.jpg")):
    ...  # skip or flag
```

Runs two checks in order:

1. **Universal** — empty file (`st_size == 0`) or unreadable path.
2. **Format** — deep structural validation for registered types via the `checkers/` registry
   (Pillow for images, CRC check for ZIP containers, header + EOF marker for PDF).
   Files with unregistered extensions pass by default.

Returns `True` if the file is likely corrupt; `False` if it passes all applicable checks.

---

### `classifer.py` — Two-Stage Screening Pipeline

```python
from classifer import Classifier
from pathlib import Path

clf = Classifier(db_path=Path("backup.db"))
result = clf.classify(file=Path("incoming.jpg"), dest_path=Path("backup/incoming.jpg"), use_ml=True)

print(result.verdict)     # ClassificationVerdict.ACCEPTED / REJECTED / NEEDS_REVIEW
print(result.confidence)  # pr(remove) when ML ran, else 0.0
```

**Stage 1 — Exact duplicate (always runs)**

Content hash (`xxh3_128`) lookup against the `files` SQLite table. Every new file is registered
on first sight; byte-identical repeats are rejected without running the ML stage.

**Stage 2 — ML image classifier (opt-in via `use_ml=True`)**

Passes the file through `classify_image()` (MobileNetV3-Large). Three outcomes:

| Condition | Verdict |
|---|---|
| `pr(remove) > 0.95` | `REJECTED` — confidently unwanted, discard automatically |
| `0.5 < pr(remove) ≤ 0.95` | `NEEDS_REVIEW` — argmax says "remove" but unsure; ask the user |
| `pr(remove) ≤ 0.5` | `ACCEPTED` — keep the file |

Non-image files and files that fail to open are always `ACCEPTED` (ML is skipped gracefully).

**SQLite schema**

```sql
files (
    file_path         TEXT  PRIMARY KEY,   -- every file registered (Stage 1)
    file_name         TEXT  NOT NULL,
    file_hash_content BLOB  NOT NULL       -- xxh3_128 digest (16 bytes)
);
CREATE INDEX idx_content_hash ON files(file_hash_content);

visual_groups (
    file_hash_visual  INTEGER  PRIMARY KEY,  -- founding dHash = group ID (reserved)
    best_path         TEXT     NOT NULL,
    file_name         TEXT     NOT NULL,
    quality_score     REAL     NOT NULL
);
```

---

### `image_classifer.py` — ML Image Classifier

```python
from image_classifer import classify_image, ClassificationVerdict
from pathlib import Path

result = classify_image(Path("photo.jpg"))
# result.verdict: ClassificationVerdict enum
# result.confidence: float — pr(remove)
```

**Model:** MobileNetV3-Large backbone with a custom two-class head (keep / remove).
The model is loaded once as a process-wide singleton on first call (double-checked locking)
and reused for all subsequent calls — avoids re-deserializing weights on every backup file.

**Device selection:** CUDA if available, otherwise CPU (`torch.device("cuda" if ... else "cpu")`).

**Thresholds** (module constants):
- `_REMOVE_THRESHOLD = 0.95` — auto-reject above this
- `_REVIEW_THRESHOLD = 0.5` — flag for review above this

---

### `file_duplicates.py` — Content-Hash Duplicate Detection

Used internally by `Classifier.classify()` (Stage 1).

Computes an `xxh3_128` hash of the file's content, then checks it against the `files` table.
If the hash is new, the file's path and hash are registered. If the hash exists, the file is
a byte-identical duplicate.

---

### `quality.py` — Image Quality Scoring

Produces a composite quality score for an image used by the visual-similarity grouping to
decide which copy of a near-duplicate group is the "best" to keep.

---

### `similar_photos.py` — Perceptual-Hash Visual Grouping

Groups visually similar photos using dHash (difference hash). Used to surface near-duplicates
(same shot, slightly different exposure or crop) during a backup review session.

---

### `checkers/` — Format-Specific Corruption Checkers

| Module | File types | Check |
|---|---|---|
| `checkers/image.py` | `.jpg`, `.png`, `.webp`, … | Pillow open + `verify()` |
| `checkers/pdf.py` | `.pdf` | Header (`%PDF-`) + EOF marker (`%%EOF`) |
| `checkers/zip_based.py` | `.zip`, `.apk`, `.docx`, … | CRC integrity check on all members |
| `checkers/registry.py` | — | Maps extensions → checker functions |

New format checkers are registered in `checkers/registry.py`. The `detector.is_corrupt()`
function looks up the extension there and falls back to "not corrupt" for unknown types.

---

## Dependencies

```
torch          # ML inference (MobileNetV3-Large)
torchvision    # Model weights + transforms
Pillow         # Image open/verify
xxhash         # xxh3_128 content hashing
numpy          # Array operations in quality scoring
```

### Installation

```bash
pip install -r requirements.txt
```

### Testing

```bash
pytest FileDetection/
```

Run from the repo root. The `tests/` directory uses pytest.

### Pretrained weights and dataset

`model.pth` (MobileNetV3-Large weights) and a `dataset/` directory of training images are present in the repo root of this module.

---

## Integration with BackupService

`BackupService` (`desktop/services/backup.py`) holds a `Classifier` instance for the duration
of a backup session. For each incoming file it calls:

```python
result = classifier.classify(cached_file, dest_path, use_ml=True)

if result.verdict is ClassificationVerdict.REJECTED:
    # skip — duplicate or confidently unwanted
elif result.verdict is ClassificationVerdict.NEEDS_REVIEW:
    # queue for user review dialog (BackupReviewDialog)
else:
    # move to destination
```

The `BackupViewModel` surfaces `NEEDS_REVIEW` items to the user via `BackupClassificationReviewDialog`.
