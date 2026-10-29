# Leaf / lesion segmentation and affected-area measurement

**Status: pipeline implemented and unit-tested, but blocked by missing data.** No trained segmentation weights ship with the repository, because no pixel-level annotations are available. Until a model is trained and evaluated on real annotated masks, the app reports the affected area as **"not measured"**. It does not fall back to an estimate.

## 1. Why the old "severity" was removed

Earlier versions thresholded the Grad-CAM attention map at 0.5 and reported the result as:
- `affected_area_pct`: the share of hot pixels in the *whole 224×224 image*, background included;
- `mild` / `moderate` / `severe`, using the unvalidated cut-offs 15 % / 40 %.

That number measures where the classifier looked. It does not measure diseased tissue, so it is not a disease measurement:
- the denominator included the background;
- Grad-CAM is a coarse 7×7 map, upsampled;
- the min–max normalisation always produces some "hot" area, even for a perfectly healthy leaf.

What happens to it now:
- **Removed** from the pipeline (`ai/explainability/severity.py` was deleted).
- **Old rows:** migration `0003` sets `severity_method='legacy_gradcam_threshold'` on stored rows that carry such a value.
- **UI and PDF:** these show the value only as a *"legacy estimate — not a measurement"*, and never use it in comparisons or charts.

## 2. Approach

The model is a compact **U-Net** (`ai/segmentation/model.py`). It does pure-PyTorch semantic segmentation with three classes:

| value | meaning |
|---|---|
| 0 | background (anything that is not visible leaf tissue) |
| 1 | visible leaf tissue without visible lesion |
| 2 | visible lesion on a leaf (lesion pixels are part of the leaf) |
| 255 | ignore / unannotated (excluded from loss, metrics and area) |

I chose it over YOLO-seg and transformer models for three reasons:
- the affected-area formula needs per-pixel *semantic* labels, not instances;
- it adds no new dependency;
- it trains on CPU for small annotated sets.

`base_channels` and the input size are configurable for larger GPU training.

**Affected area** (`ai/segmentation/masks.py`) is computed as:

```
affected_area_pct = lesion pixels on leaf / visible leaf pixels × 100
visible leaf pixels = pixels labelled 1 or 2   (background and 255 never count)
```

**Rules the code enforces** (unit-tested in `ai/tests/test_segmentation_and_knowledge.py`):
- The result is "unavailable" (`leaf_not_identified`) when the leaf covers less than 2 % of the image.
- When two separate binary masks are given, lesion pixels outside the leaf mask are not counted. If more than 5 % of the lesion lies outside the leaf, the masks are rejected as `inconsistent_masks`.
- Multiple leaves and disconnected lesions are handled; their connected regions are counted with `scipy.ndimage.label`.
- The original photo is never modified. The service writes a separate class-map PNG and an RGBA overlay (leaf green, lesion magenta). Both are served only through signed URLs.
- Every measurement stores the segmentation **method** and **model version**: `<run dir>:<sha256 of weights[:12]>`.

**Severity categories.** A percentage is mapped to mild / moderate / severe only if an operator configures a **documented, crop-specific scale with a source citation** (`AGRIGUARD_SEVERITY_SCALES_FILE`; see `ai/segmentation/severity_scales.py`). The default registry is empty, so the UI shows the measured percentage and states that categories require calibration.

## 3. Data: what exists and what is needed

- **In the repository:** `datasets/plantwild_v2` has **image-level labels only**: 115 disease classes. It has **no masks and no polygons**. Image-level labels are never converted into "masks".
- **Public candidate:** *PlantSeg* (Wei et al., 2024, arXiv:2409.04038) is an in-the-wild plant-disease segmentation dataset, described as about 11,400 images with disease segmentation masks plus about 8,000 healthy-plant images. It is published on Zenodo (record 16665770, file `Plantseg.zip`, about 1.7 GB).
  - It could not be downloaded or inspected here: zenodo.org and arxiv.org are blocked by this environment's network policy.
  - **Before use, verify** three things:
    - its licence;
    - whether its classes align with this project's labels;
    - whether it includes **leaf** masks as well as lesion masks. The descriptions available here mention disease masks only. Without leaf masks, the leaf-area denominator still needs leaf annotations or a separately trained and validated leaf model.
- **Needed for a trustworthy model:** images from your own field conditions with **both** leaf and lesion annotations, split by plant/field to avoid leakage. As rough guidance, 300–500 annotated images are enough to start; a few thousand across crops and lighting are needed to report per-crop results.

## 4. Annotation workflow

1. **Annotate** in CVAT, Label Studio, or LabelMe with two polygon labels:
   - `leaf`: outline each visible leaf; overlapping leaves are separate polygons;
   - `lesion`: outline each visible lesion inside a leaf.

   Leave regions you cannot judge unannotated.
2. **Export** in COCO format (polygons, not RLE).
3. **Convert:**

   ```bash
   python -m ai.segmentation.convert_coco --coco export/annotations.json --images-dir export/images \
       --out datasets_segmentation/field_set_2026 --leaf-categories leaf --lesion-categories lesion
   ```

   - Lesion pixels outside every leaf become 255 (ignore) and are counted in the output, so annotators can fix them.
   - Images without a leaf polygon are skipped.
4. **Expected layout:** `datasets_segmentation/<name>/images/<stem>.jpg` and `datasets_segmentation/<name>/masks/<stem>.png`. Masks are validated before training (label values, size equal to the image).
5. **Train** (refuses to run with fewer than `--min-images`, default 50):

   ```bash
   python -m ai.segmentation.train --seg-root datasets_segmentation --epochs 40
   ```

   - The split is deterministic, by image hash (exact duplicates share a split), 70/15/15.
   - The run is saved to `artifacts/segmentation/runs/<ts>_unet/` and marked as latest. The backend picks it up on restart.
6. **Evaluate** on the held-out test split:

   ```bash
   python -m ai.segmentation.evaluate
   ```

   - It reports per-class IoU and Dice, mean IoU and Dice, pixel accuracy, and the **affected-area mean absolute error in percentage points** (the number users see).
   - It lists the ten worst images by lesion IoU. Inspect them for poor lighting, overlapping leaves, complex backgrounds and small lesions.
   - The resulting `evaluation_test.json` also provides the **measurement tolerance** that the observation-comparison feature uses. Without it, changes between two observations are reported as *"not established"*.

## 5. Evaluation results

**None: no annotated masks are available.** Do not interpret any segmentation output as accurate until step 6 has been run on real held-out annotations.
