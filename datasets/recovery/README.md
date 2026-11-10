# Recovery dataset (longitudinal plant monitoring)

Repeated photos of the same plants over time, with optional annotations, used to
**calibrate** the recovery assessment rules (not to train a neural network).
Full schema: [docs/datasets/recovery-dataset-schema.md](../../docs/datasets/recovery-dataset-schema.md).

```
raw/
  plants/plants.csv                  plant_id, crop[, species, region, notes]
  scans/scans.csv                    scan_id, plant_id, scan_date, image_file[, disease_label, severity_label,
                                     affected_area_pct, mask_file, treatment_stage]
  scans/<image files>                referenced by image_file
  treatments/treatments.csv          treatment_id, plant_id, applied_on, category, name[, notes]
  annotations/recovery_labels.csv    plant_id, from_scan_id, to_scan_id, status[, annotator_id, notes]
  annotations/<mask files>           optional, referenced by mask_file
processed/  manifests/  reports/     written by the tools
schemas/recovery.schema.json         column definitions
samples/                             CSV header templates
```

- No personal data is needed: ids are opaque, `region` is optional and coarse.
- `status` ∈ improving | stable | worsening | inconclusive (see the schema doc for how to judge).
- `affected_area_pct` on both scans of a labeled pair is what calibration uses.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\recovery-data.ps1 -Action validate
powershell -ExecutionPolicy Bypass -File scripts\recovery-data.ps1 -Action calibrate
```
