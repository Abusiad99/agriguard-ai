"""Fixed guidance text shared by the diagnosis API and the reports.

GENERIC_PREVENTION_ADVICE is general good practice shown with any disease that is in
the knowledge base. It is NOT disease-specific and has no cited source; reports label
it "general guidance" accordingly (see docs/features/reports.md).
"""
from __future__ import annotations

GENERIC_PREVENTION_ADVICE = (
    "Ensure proper irrigation and ventilation.",
    "Remove and destroy infected plant material.",
    "Practice crop rotation and field sanitation.",
)

# Stable codes for the items above, in the same order, so clients can show them in the
# reader's language (the API also returns the English text for older clients).
GENERIC_PREVENTION_CODES = ("irrigation_ventilation", "remove_infected_material", "rotation_sanitation")
assert len(GENERIC_PREVENTION_CODES) == len(GENERIC_PREVENTION_ADVICE)
