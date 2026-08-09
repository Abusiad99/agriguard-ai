# AgriGuard AI — Use Cases

## Actors
- **Farmer** (registered end user)
- **Agronomist** (knowledge-base curator)
- **Admin** (system administrator)
- **Weather API** (external system actor)
- **AI Pipeline** (internal system actor, referenced within use cases for clarity)

## UC-01: Register Account
- **Actor**: Farmer
- **Preconditions**: User is not authenticated.
- **Main Flow**:
  1. User navigates to Register.
  2. User submits email, password, full name.
  3. System validates uniqueness of email and password strength.
  4. System creates account with role `farmer`, hashes password.
  5. System returns success and prompts login.
- **Alternate Flow**: Email already exists → system returns a validation error, no account created.
- **Postconditions**: New user record exists in `users` table.

## UC-02: Log In
- **Actor**: Farmer, Agronomist, Admin
- **Main Flow**:
  1. User submits email + password.
  2. System verifies credential hash.
  3. System issues JWT access + refresh token.
- **Alternate Flow**: Invalid credentials → generic "invalid email or password" error (no user
  enumeration).

## UC-03: Scan Plant (Core Use Case)
- **Actor**: Farmer
- **Preconditions**: User authenticated.
- **Main Flow**:
  1. User selects "Scan Plant".
  2. User captures a photo or uploads an image.
  3. System validates the image (FR-SCAN-2).
  4. System submits image to AI Pipeline.
  5. AI Pipeline executes Steps 1–8 (identification → treatment recommendation).
  6. System calls Weather API for the user's location (Step 9).
  7. AI Pipeline/System generates agricultural recommendation (Step 10).
  8. System generates PDF report (Step 11).
  9. System persists the diagnosis to history (BR2).
  10. System displays the Results Page.
- **Alternate Flows**:
  - A1 (low plant-ID confidence): pipeline halts after Step 1; system shows "unrecognized plant".
  - A2 (weather API unavailable): Steps 9–10 weather-derived content omitted; pipeline still
    completes and produces a report (NFR-AVAIL-2).
  - A3 (low disease-classification confidence): result flagged "Low Confidence — Recommend Manual
    Expert Review" per BR1.
- **Postconditions**: A new immutable diagnosis record exists; a PDF report is available for
  download.

## UC-04: View Results
- **Actor**: Farmer
- **Preconditions**: UC-03 has completed successfully.
- **Main Flow**: System displays all fields defined in FR-RESULT-1/2.

## UC-05: Download PDF Report
- **Actor**: Farmer
- **Preconditions**: A completed diagnosis exists.
- **Main Flow**: User taps "Download Report"; system streams the previously generated PDF (or
  regenerates it if not cached) to the client.

## UC-06: View & Search History
- **Actor**: Farmer
- **Main Flow**:
  1. User opens History.
  2. System lists past diagnoses, most recent first.
  3. User filters by plant, disease, or date range.
  4. System returns matching records.

## UC-07: Compare Scans
- **Actor**: Farmer
- **Preconditions**: At least two prior scans exist.
- **Main Flow**: User selects two history entries; system renders a side-by-side comparison of
  severity, confidence, and diagnosis over time.

## UC-08: View Dashboard
- **Actor**: Farmer, Agronomist, Admin
- **Main Flow**: System aggregates and displays total scans, healthy/diseased counts, palm disease
  statistics, most common diseases, and monthly charts, scoped to the user's own data (Farmer) or
  system-wide (Admin/Agronomist, per FR-ADMIN-4).

## UC-09: Manage Disease Knowledge Base
- **Actor**: Agronomist, Admin
- **Main Flow**:
  1. Actor opens Admin Panel → Manage Diseases.
  2. Actor creates/edits/archives a disease entry (description, symptoms, causes, transmission,
     severity mapping).
  3. System validates required fields and persists the change as a new version (NFR-DATA-1
     append-only semantics apply to knowledge-base edits as well, for audit purposes).

## UC-10: Manage Treatments
- **Actor**: Agronomist, Admin
- **Main Flow**: Same shape as UC-09, but for treatment entries; system enforces BR6 — a chemical
  treatment cannot be published without a `source_citation` unless explicitly marked
  "authority-referral-only".

## UC-11: Manage Users
- **Actor**: Admin
- **Main Flow**: Admin lists users, can deactivate an account or change its role. System logs the
  action with the acting admin's ID for audit purposes.

## UC-12: View System Reports & Analytics
- **Actor**: Admin
- **Main Flow**: Admin views/exports system-wide scan volume, disease frequency, and user growth
  analytics.

## UC-13: Train AI Models (Offline/Operational Use Case)
- **Actor**: Developer/Admin (operational, not end-user-facing)
- **Preconditions**: One or more supported datasets placed under `datasets/`.
- **Main Flow**:
  1. Operator runs `python train.py`.
  2. System audits `datasets/`, fails fast with an actionable message if nothing usable is found
     (C2).
  3. System discovers, parses, and merges datasets (FR-DATA-1..3).
  4. System deduplicates, balances, splits, and augments data (FR-DATA-4..6).
  5. System trains each required model, evaluates on the validation/test splits, and persists all
     artifacts (FR-DATA-7..8).
- **Postconditions**: A new timestamped model-run directory exists with weights, encoders, metrics,
  confusion matrices, and training curves, ready to be loaded by the inference service.

## Use Case Summary Table
| ID | Name | Primary Actor |
|---|---|---|
| UC-01 | Register Account | Farmer |
| UC-02 | Log In | Farmer/Agronomist/Admin |
| UC-03 | Scan Plant | Farmer |
| UC-04 | View Results | Farmer |
| UC-05 | Download PDF Report | Farmer |
| UC-06 | View & Search History | Farmer |
| UC-07 | Compare Scans | Farmer |
| UC-08 | View Dashboard | Farmer/Agronomist/Admin |
| UC-09 | Manage Disease Knowledge Base | Agronomist/Admin |
| UC-10 | Manage Treatments | Agronomist/Admin |
| UC-11 | Manage Users | Admin |
| UC-12 | View System Reports & Analytics | Admin |
| UC-13 | Train AI Models | Developer/Admin (operational) |
