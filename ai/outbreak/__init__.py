"""Disease outbreak risk estimation (see docs/features/outbreak-prediction.md).

Shared by the training pipeline and the backend so features are computed identically:
grid (geographic aggregation), features (feature engineering), suitability (sourced
environmental rules), model (trained-model inference).
"""
