# Evaluation record: `20261029T210637Z_efficientnet_b0`

A copy of the outputs from the training run described in [AI_RELIABILITY.md](../../AI_RELIABILITY.md), kept in the repository as evidence. The model weights are not included. To reproduce, run `python train.py` and `python evaluate.py`.

| File | What it is |
|---|---|
| `report.md`, `report.json` | Held-out test evaluation (`python evaluate.py`, git `34d321d6c3`) |
| `per_class_metrics.csv` | Precision, recall, F1 and support for each of the 115 classes |
| `confusion_matrix.csv` | Rows are true classes, columns are predictions |
| `reliability_diagram.png` | Test-set calibration before and after temperature scaling |
| `risk_coverage.png` | Accuracy on the answered images as fewer, more confident images are answered |
| `calibration.json` | Temperature and decision thresholds, selected on the validation split |
| `training_history.json` | Loss and accuracy per epoch |
