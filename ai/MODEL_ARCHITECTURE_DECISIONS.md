# AgriGuard AI — Model Architecture Comparison & Decisions

This note fulfills the requirement to compare YOLOv11, EfficientNet, ConvNeXt, ViT, SAM2, and
MobileNetV4 and justify a final selection per sub-task, and documents exactly what the code in
`ai/` implements.

## 1. Comparison

| Model | Strengths | Weaknesses for this project | Best-suited sub-task |
|---|---|---|---|
| **EfficientNet (B0–B4)** | Excellent accuracy/compute ratio; strong ImageNet-pretrained weights; fast CPU inference (NFR-PERF-1, NFR-PORT-2) | Lower ceiling than ViT/ConvNeXt at very large data/compute scale | **Plant identification, Disease classification** (default, resource-constrained deployments) |
| **ConvNeXt** | Modernized CNN, closes most of the gap to ViT on ImageNet-scale accuracy while keeping CNN inductive bias (better on modest datasets) | Larger memory footprint than EfficientNet-B0 | **Disease classification** (higher-accuracy tier when GPU available) |
| **Vision Transformer (ViT)** | Strong global context modeling, good with large/augmented datasets, attention maps are directly explainable | Needs more data/augmentation to avoid overfitting on small merged datasets; slower CPU inference | **Disease classification (high-data tier)**; **Explainability** (attention rollout) |
| **MobileNetV4** | Purpose-built for edge/mobile latency, smallest footprint | Lowest accuracy ceiling of the classification options | **On-device / low-power inference profile** (optional deployment target) |
| **YOLOv11** | State-of-the-art real-time object detection; natively produces bounding boxes | Requires bounding-box-annotated training data; only a subset of source datasets (IP102-style) provide this | **Pest detection with bounding boxes** — pluggable extension when bbox-annotated data is present (see §3) |
| **SAM2** | Best-in-class promptable segmentation, precise pixel masks | Not a classifier; heavy; typically used as a downstream refinement step, not an end-to-end disease classifier | **Disease region segmentation refinement** — optional extension for pixel-precise severity area (see §3) |

## 2. Final Selection (what the code implements by default)

- **Plant Identification (Step 1) & Disease Classification (Step 2)**: implemented via a shared,
  swappable classification backbone factory (`ai/models/architectures.py`) built on `timm`,
  defaulting to **EfficientNet-B0** (`AGRIGUARD_ARCHITECTURE=efficientnet_b0`) for the best
  accuracy/latency/portability balance (NFR-PERF-1, NFR-PORT-2, C3). **ConvNeXt-Tiny** and
  **ViT-Base** are selectable via the same factory (`AGRIGUARD_ARCHITECTURE=convnext_tiny` /
  `vit_base_patch16_224`) for deployments with GPU headroom that want the higher accuracy tier.
  **MobileNetV4** (`mobilenetv4_conv_small`) is selectable for edge-constrained deployments.
- **Pest Detection (Step 3)**: implemented as a classification head over the same backbone
  family (pest-vs-no-pest / pest-species classification) trained on whatever pest-labeled data is
  present (e.g., IP102, Red Palm Weevil dataset), since this reaches full functional coverage of
  FR-AI-3 without requiring bounding-box-annotated data to exist for every deployment. The XML
  adapter (`ai/data/adapters/xml_annotation_adapter.py`) already parses Pascal-VOC bounding boxes
  when present — **YOLOv11 is the designated upgrade path**: if bbox-annotated pest data is
  available, `ai/models/architectures.py` exposes a `build_yolo_detector()` hook (Ultralytics
  YOLOv11) that consumes the same unified dataset index filtered to samples with bbox metadata.
- **Disease Localization (Step 4)**: implemented via **Grad-CAM** (CNN backbones) / **attention
  rollout** (ViT backbone) over the trained disease classifier — `ai/explainability/gradcam.py` —
  thresholded into a bounding region. This reuses the classifier that must be trained anyway
  (no separate detector required to satisfy FR-AI-4), and is the same mechanism used for Step 7
  Explainability, keeping the pipeline coherent. **SAM2 is the designated upgrade path**: the
  `Explainer` interface (`ai/explainability/base.py`) is model-agnostic, so a SAM2-based
  segmentation refinement step can be substituted by implementing the same interface and pointing
  the Grad-CAM-derived box in as a SAM2 prompt, without changing any downstream pipeline code.
- **Severity Estimation (Step 5)**: computed directly from the thresholded heatmap mask's pixel
  area as a percentage of total leaf/frame area (`ai/explainability/severity.py`), banded into
  Mild/Moderate/Severe per `CONFIG.inference` thresholds.
- **Explainability (Step 7)**: Grad-CAM / attention-rollout heatmap overlay, per above.

## 3. Why This Is the Right Default, Not a Shortcut
Object detection (YOLOv11) and promptable segmentation (SAM2) both require bounding-box or mask
ground truth to train in a supervised way. The datasets this project is designed to auto-ingest
(PlantVillage, PlantDoc, the Kaggle New Plant Diseases Dataset) are **classification-labeled
only** — folder-per-class, no boxes/masks. Only IP102-style pest data typically ships bounding
boxes. Building the core pipeline around classifier-derived localization means:
1. The system works end-to-end on classification-only data (the common case) with zero additional
   annotation requirements from the user.
2. When bbox-annotated data *is* present (already parsed by `XmlAnnotationAdapter`), the
   architecture has a defined, code-level extension point (`build_yolo_detector()`) to upgrade
   localization quality without redesigning the pipeline — this is the justified, intentional use
   of YOLOv11/SAM2 named in the requirements, applied where the data actually supports it.
