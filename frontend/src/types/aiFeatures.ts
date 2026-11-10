/**
 * Types for the AI features (model registry, disease localization, plant recovery,
 * outbreak risk). Source of truth: backend/app/interface/schemas/ai_features_schemas.py
 * and backend/app/application/services/outbreak_service.py.
 */

// ---------- Model registry ----------
export type Readiness =
  | "not_configured"
  | "dataset_unavailable"
  | "not_trained"
  | "training_required"
  | "ready"
  | "insufficient_data"
  | "unavailable"
  | "error";

export interface ModelCard {
  task: "classification" | "segmentation" | "outbreak";
  readiness: Readiness;
  message: string;
  name?: string | null;
  version?: string | null;
  architecture?: string | null;
  dataset_version?: string | null;
  training_status?: string | null;
  trained_at?: string | null;
  classes: string[];
  metrics: Record<string, unknown>;
}

// ---------- Disease localization ----------
export interface SegmentationClass {
  id: number;
  name: string;
  kind: "background" | "leaf" | "disease";
  color: [number, number, number] | number[];
}

export interface SegmentationRegion {
  label: string;
  class_id: number;
  pixels: number;
  bbox: { x_min: number; y_min: number; x_max: number; y_max: number };
  mean_confidence?: number | null;
}

export interface Segmentation {
  /** "ok", or why no segmentation is available (readiness value / "failed"). */
  status: Readiness | "ok" | "failed";
  message?: string | null;
  model_name?: string | null;
  model_version?: string | null;
  image_width?: number | null;
  image_height?: number | null;
  mask_width?: number | null;
  mask_height?: number | null;
  affected_pixels?: number | null;
  plant_pixels?: number | null;
  affected_area_pct?: number | null;
  area_basis?: string | null;
  area_unavailable_reason?: string | null;
  mean_confidence?: number | null;
  mean_uncertainty?: number | null;
  classes: SegmentationClass[];
  regions: SegmentationRegion[];
  artifacts?: { mask: string; overlay: string; contours: string } | null;
  created_at?: string | null;
}

export interface ImageQuality {
  width: number;
  height: number;
  mean_luma: number;
  sharpness: number;
  issues: ("too_small" | "too_dark" | "overexposed" | "blurry")[];
  acceptable: boolean;
}

// ---------- Plant recovery ----------
export type RecoveryStatus = "improving" | "stable" | "worsening" | "inconclusive" | "insufficient_data";
export type TreatmentStage = "before_treatment" | "during_treatment" | "after_treatment" | "unknown";
export type TreatmentCategoryRecorded = "organic" | "chemical" | "biological" | "cultural" | "other";

export interface TrackedPlant {
  id: string;
  name: string;
  crop?: string | null;
  species?: string | null;
  notes?: string | null;
  status: "active" | "archived";
  latitude?: number | null;
  longitude?: number | null;
  initial_diagnosis_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  scan_count: number;
  last_scan_at?: string | null;
  latest_status?: RecoveryStatus | null;
  next_reminder_on?: string | null;
}

export interface PlantScan {
  diagnosis_id: string;
  diagnosed_at?: string | null;
  treatment_stage: TreatmentStage;
  notes?: string | null;
  predicted_condition?: string | null;
  is_healthy?: boolean | null;
  confidence_score?: number | null;
  low_confidence_flag: boolean;
  image_url?: string | null;
  image_quality?: ImageQuality | null;
  segmentation_status?: string | null;
  affected_area_pct?: number | null;
  segmentation_model?: string | null;
}

export interface Assessment {
  id?: string | null;
  status: RecoveryStatus;
  method_version: string;
  baseline_diagnosis_id?: string | null;
  latest_diagnosis_id?: string | null;
  indicators: { code: string; [key: string]: unknown }[];
  limitations: string[];
  area_series: { diagnosis_id: string; taken_at: string; area_pct: number; model: string }[];
  summary?: string | null;
  created_at?: string | null;
}

export interface TreatmentRecord {
  id: string;
  name: string;
  category: TreatmentCategoryRecorded;
  applied_on: string;
  application_notes?: string | null;
  dosage_text?: string | null;
  documentation_ref?: string | null;
  follow_up_on?: string | null;
  user_notes?: string | null;
  created_at?: string | null;
  source: "user_recorded";
}

export interface Reminder {
  id: string;
  tracked_plant_id: string;
  plant_name?: string | null;
  kind: "next_scan" | "treatment_follow_up";
  due_on: string;
  status: "pending" | "completed" | "dismissed";
  state: "pending" | "overdue" | "completed" | "dismissed";
  note?: string | null;
  treatment_record_id?: string | null;
  completed_at?: string | null;
}

export interface TimelineEvent {
  id: string;
  event_type: string;
  occurred_at: string;
  diagnosis_id?: string | null;
  treatment_record_id?: string | null;
  reminder_id?: string | null;
  assessment_id?: string | null;
  details?: Record<string, unknown> | null;
}

export interface Paginated<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface TrackedPlantDetail {
  plant: TrackedPlant;
  scans: PlantScan[];
  assessment: Assessment;
  treatments: TreatmentRecord[];
  reminders: Reminder[];
}

export interface CompareResult {
  first: PlantScan;
  second: PlantScan;
  checks: { days_between?: number; resolution_ratio?: number; lighting_difference?: number; classification_changed?: { from: string; to: string } };
  area_change?: { from: number; to: number; change_pct_points: number; model: string } | null;
  limitations: string[];
}

// ---------- Outbreak risk ----------
export type RiskLevel = "low" | "moderate" | "high" | "critical" | "insufficient_data" | "unavailable";

export interface GeoArea {
  id: string;
  grid_key: string;
  resolution_deg: number;
  bounds: { south: number; west: number; north: number; east: number };
  center: { lat: number; lon: number };
  name?: string | null;
}

export interface PredictionSummary {
  prediction_id: string;
  status: "ok" | "insufficient_data";
  risk_level: RiskLevel;
  score?: number | null;
  score_kind?: "calibrated_probability" | "risk_score" | null;
  confidence_level?: "low" | "medium" | "high" | null;
  data_completeness?: number | null;
  model_name?: string | null;
  model_version?: string | null;
  horizon_days: number;
  created_at?: string | null;
  forecast_end?: string | null;
}

export interface AreaCounts {
  app_inspections: number | null;
  app_positives: number | null;
  dataset_inspections: number;
  dataset_positives: number;
  app_counts_suppressed: boolean;
  inspections: number;
  positives: number;
  positive_rate: number | null;
  latest_observation: string | null;
}

export interface MapCell extends AreaCounts {
  area: GeoArea;
  prediction: PredictionSummary | null;
}

export interface MapLayer {
  cells: MapCell[];
  total_areas: number;
  page: number;
  page_size: number;
  hidden_for_privacy: number;
  filters: { crop: string | null; disease: string | null; date_from: string; date_to: string; horizon_days: number };
  privacy: { min_contributors: number; grid_resolution_deg: number };
  generated_at: string;
}

export interface OutbreakReadiness {
  model: ModelCard;
  data: {
    app_scan_observations: number;
    dataset_observations: number;
    areas_with_observations: number;
    first_observation: string | null;
    last_observation: string | null;
    located_diagnoses: number;
  };
  suitability_profiles: { id: string; crop: string; disease: string; source: string }[];
  privacy: { grid_resolution_deg: number; min_contributors: number };
  can_predict: boolean;
  limitations: string[];
  generated_at: string;
}

export interface OutbreakFilters {
  crops: string[];
  pairs: { crop: string; disease: string; model_trained: boolean }[];
  horizons_days: number[];
}

export interface WeatherDay {
  day: string;
  kind: "observed" | "forecast";
  source: string;
  temperature_mean_c: number | null;
  temperature_min_c: number | null;
  temperature_max_c: number | null;
  relative_humidity_mean_pct: number | null;
  rh_hours_ge_90: number | null;
  precipitation_mm: number | null;
}

export interface SuitabilityResult {
  status: "met" | "not_met" | "insufficient_weather_data";
  periods: { start: string; end: string }[];
  missing_days: string[];
  profile_id: string;
  rule: string;
  source: string;
  description: string;
  window: { start: string; end: string };
  kind: "rule_based_suitability";
}

export interface AreaDetail {
  area: GeoArea;
  summary: AreaCounts | null;
  trend: { week_start: string; inspections: number; positives: number }[];
  weather: { days: WeatherDay[]; retrieved_at: string | null };
  suitability: SuitabilityResult[];
  predictions: PredictionSummary[];
  model: ModelCard;
}

export interface AreaLookup {
  area_id: string | null;
  grid_key: string;
  bounds: GeoArea["bounds"];
  center: { lat: number; lon: number };
}

export interface RiskFactor {
  feature: string;
  value: number | null;
  importance: number;
  relation: "above_typical" | "below_typical" | "typical" | "missing" | "not_in_training_data";
  typical_range?: [number | null, number | null] | null;
}

export interface PredictionResult extends Partial<Omit<PredictionSummary, "status">> {
  status: "ok" | "insufficient_data" | "model_unavailable";
  risk_level: RiskLevel;
  reason?: string;
  area: GeoArea;
  crop: string;
  disease: string;
  horizon_days: number;
  as_of: string;
  forecast_start: string;
  forecast_end: string;
  data_completeness: number;
  features: Record<string, number | null>;
  suitability: SuitabilityResult[];
  factors?: RiskFactor[];
  model: ModelCard;
  limitations: string[];
  persisted: boolean;
}
