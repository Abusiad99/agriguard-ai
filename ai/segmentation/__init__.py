"""Disease localization (semantic segmentation) — separate from the classification model.

See docs/features/disease-localization.md. Pipeline:
  validate -> preprocess -> train -> evaluate -> inference (backend).
"""

# Files written per segmented image (ai/segmentation/visualize.py), served by
# GET /api/v1/diagnoses/{id}/segmentation/{name}.
ARTIFACT_FILES = {"mask": "mask.png", "overlay": "overlay.png", "contours": "contours.png"}
