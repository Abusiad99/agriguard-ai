/**
 * TypeScript types mirroring the backend's Pydantic schemas field-for-field.
 * Source of truth: backend/app/interface/schemas/*.py and
 * docs/02-system-design/13-api-specification.md.
 *
 * Field names are kept in snake_case (matching the JSON the API actually sends)
 * rather than converted to camelCase, so there is never a silent mapping layer
 * that could drift from the backend contract.
 */

// ---------- Auth (backend/app/interface/schemas/auth_schemas.py) ----------
export type UserRole = "farmer" | "agronomist" | "admin";

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
}

export interface RegisterResponse {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface UserSummary {
  id: string;
  role: UserRole;
  full_name: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: UserSummary;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface LogoutRequest {
  refresh_token: string;
}

// ---------- Errors (API spec §1.1) ----------
export interface ErrorDetail {
  field?: string | null;
  issue: string;
}

export interface ErrorBody {
  code: string;
  message: string;
  details: ErrorDetail[];
}

export interface ApiErrorResponse {
  error: ErrorBody;
  request_id?: string | null;
}

export class ApiError extends Error {
  code: string;
  details: ErrorDetail[];
  status: number;
  requestId?: string | null;

  constructor(status: number, body: ApiErrorResponse) {
    super(body.error.message);
    this.name = "ApiError";
    this.code = body.error.code;
    this.details = body.error.details ?? [];
    this.status = status;
    this.requestId = body.request_id;
  }
}

// ---------- Diagnosis (backend/app/interface/schemas/diagnosis_schemas.py) ----------
export type SeverityLevel = "mild" | "moderate" | "severe";

export interface PlantSchema {
  name: string;
  scientific_name?: string | null;
}

export interface DiseaseSchema {
  name: string;
  type?: string | null;
  description: string;
  symptoms: string[];
  causes: string[];
  transmission_method?: string | null;
}

export interface TreatmentGroupSchema {
  instructions?: string | null;
  safety_notes?: string | null;
  source_citation?: string | null;
}

export interface TreatmentSchema {
  organic?: TreatmentGroupSchema | null;
  chemical?: TreatmentGroupSchema | null;
  biological?: TreatmentGroupSchema | null;
}

export interface PestSchema {
  name: string;
  confidence: number;
  bbox: { x_min: number; y_min: number; x_max: number; y_max: number };
}

export interface WeatherSchema {
  temperature_c?: number | null;
  humidity_pct?: number | null;
  wind_speed_kmh?: number | null;
  rain_probability_pct?: number | null;
  uv_index?: number | null;
}

export interface RecommendationSchema {
  irrigation_advice?: string | null;
  spraying_advice?: string | null;
  fertilizer_advice?: string | null;
}

// ---------- AI Agricultural Analysis (Gemini reasoning layer — backend/app/interface/schemas/ai_analysis_schemas.py) ----------
// This is an explanation/reasoning layer on top of the CV diagnosis above, never
// a replacement for it — the CV model's plant/disease/confidence/severity fields
// remain authoritative regardless of what this section contains or whether it's
// present at all.
export type CvConsistency = "consistent" | "partially_consistent" | "inconsistent" | "uncertain";
export type AnalysisUrgency = "low" | "medium" | "high";
export type AiAnalysisStatus = "ok" | "disabled" | "unavailable";

export interface GeminiAnalysisSchema {
  diagnosis_explanation: string;
  observed_symptoms: string[];
  cv_consistency: CvConsistency;
  confidence_assessment: string;
  severity_explanation: string;
  treatment_guidance: string[];
  prevention_guidance: string[];
  environmental_risk: string;
  urgency: AnalysisUrgency;
}

export interface AiAnalysisSchema {
  status: AiAnalysisStatus;
  analysis?: GeminiAnalysisSchema | null;
  message?: string | null;
}

export type DiagnosisStatus = "completed" | "unrecognized_plant";

/** confident | uncertain | inconclusive come from pipeline 2.0; "legacy" marks
 * observations created before decision statuses existed. */
export type DecisionStatus = "confident" | "uncertain" | "inconclusive" | "legacy";

export interface QualityIssue {
  code: string;
  severity: "reject" | "warning";
  message: string;
  hint: string;
  metric?: number | null;
  threshold?: number | null;
}

export interface ImageQuality {
  status: "ok" | "warning" | "rejected";
  issues: QualityIssue[];
  metrics: Record<string, number>;
  version?: string | null;
}

export interface DecisionThresholds {
  confident?: number | null;
  reject?: number | null;
  plant_mass?: number | null;
  source?: "validation" | "env_override" | "unvalidated_default" | string | null;
  temperature?: number | null;
  calibrated?: boolean | null;
}

export interface Decision {
  status?: DecisionStatus | null;
  top1_probability?: number | null;
  margin?: number | null;
  normalized_entropy?: number | null;
  plant_identified?: boolean | null;
  plant_probability_mass?: number | null;
  thresholds?: DecisionThresholds | null;
}

export interface Candidate {
  label?: string | null;
  display_name?: string | null;
  plant?: string | null;
  condition?: string | null;
  probability_pct?: number | null;
  cause_type?: string | null;
  typical_parts: string[];
  symptom_patterns: string[];
  regulated_in_many_regions: boolean;
  has_knowledge_base_entry: boolean;
}

export interface Hint {
  code: string;
  kind: "consistent" | "also_check";
}

export interface Differential {
  version?: string | null;
  taxonomy_version?: string | null;
  model_candidates: Candidate[];
  also_consider: string[];
  not_assessable_by_model: string[];
  follow_up_questions: string[];
  answers: Record<string, string | string[]>;
  hints: Hint[];
  expert_review_recommended: boolean;
  expert_review_reasons: string[];
  regulated_candidates: string[];
}

export interface Explanation {
  method?: string | null;
  available: boolean;
  reason?: string | null;
  target_label?: string | null;
  image_url?: string | null;
}

export interface AreaMeasurement {
  status: string;
  affected_area_pct?: number | null;
  healthy_area_pct?: number | null;
  leaf_pixels: number;
  lesion_pixels: number;
  leaf_fraction_of_image: number;
  leaf_regions: number;
  lesion_regions: number;
  reason?: string | null;
}

export interface Segmentation {
  status: "measured" | "unavailable" | string;
  reason?: string | null;
  method?: string | null;
  model_version?: string | null;
  measurement?: AreaMeasurement | null;
  severity: { level?: string | null; basis?: string | null; source?: string | null };
  overlay_url?: string | null;
  mask_url?: string | null;
}

export type MeasurementBasis = "segmentation" | "legacy_attention_estimate";

export interface DiagnosisResponse {
  diagnosis_id: string;
  status: DiagnosisStatus;
  plant?: PlantSchema | null;
  disease?: DiseaseSchema | null;
  confidence_score: number;
  severity_level?: SeverityLevel | null;
  affected_area_pct?: number | null;
  healthy_area_pct?: number | null;
  roi_image_url?: string | null;
  heatmap_image_url?: string | null;
  low_confidence_flag: boolean;
  pests_detected: PestSchema[];
  treatment?: TreatmentSchema | null;
  prevention_advice: string[];
  recovery_probability?: number | null;
  estimated_recovery_time?: string | null;
  weather?: WeatherSchema | null;
  recommendation?: RecommendationSchema | null;
  report_url?: string | null;
  diagnosed_at?: string | null;
  ai_analysis?: AiAnalysisSchema | null;

  decision_status?: DecisionStatus | null;
  is_legacy?: boolean;
  predicted_label?: string | null;
  predicted_display_name?: string | null;
  decision?: Decision | null;
  image_quality?: ImageQuality | null;
  original_image_url?: string | null;
  explanation?: Explanation | null;
  segmentation?: Segmentation | null;
  severity_method?: string | null;
  measurement_basis?: MeasurementBasis | null;
  differential?: Differential | null;
  model_version?: string | null;
  pipeline_version?: string | null;
  plant_profile?: { id: string; name: string } | null;
  limitations: string[];
}

export interface ScanRejectedResponse {
  diagnosis_id?: string | null;
  status: "rejected_image_quality";
  message: string;
  quality: ImageQuality;
}

export interface UnrecognizedPlantResponse {
  diagnosis_id?: string | null;
  status: "unrecognized_plant";
  message: string;
}

export type ScanResponse = DiagnosisResponse | UnrecognizedPlantResponse | ScanRejectedResponse;

export function isUnrecognizedPlant(r: ScanResponse): r is UnrecognizedPlantResponse {
  return r.status === "unrecognized_plant";
}

export function isQualityRejected(r: ScanResponse): r is ScanRejectedResponse {
  return r.status === "rejected_image_quality";
}

export interface DiagnosisSummarySchema {
  id: string;
  plant?: string | null;
  disease?: string | null;
  severity_level?: SeverityLevel | null;
  confidence_score: number;
  thumbnail_url?: string | null;
  diagnosed_at?: string | null;
  decision_status?: DecisionStatus | null;
  predicted_label?: string | null;
  predicted_display_name?: string | null;
  plant_profile_id?: string | null;
  plant_profile_name?: string | null;
  affected_area_pct?: number | null;
  measurement_basis?: MeasurementBasis | null;
  image_quality_status?: string | null;
}

export interface PaginatedDiagnosesResponse {
  items: DiagnosisSummarySchema[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ObservationComparison {
  earlier_id: string;
  later_id: string;
  same_plant: boolean;
  days_between?: number | null;
  prediction_change: "same_prediction" | "different_prediction" | "prediction_unavailable";
  earlier_prediction?: string | null;
  later_prediction?: string | null;
  measurement: {
    status: string;
    reason?: string | null;
    earlier_pct?: number | null;
    later_pct?: number | null;
    delta_pct_points?: number | null;
    tolerance_pct_points?: number | null;
  };
  comparability_issues: string[];
  summary: "visible_area_increased" | "visible_area_decreased" | "no_clear_change_in_measurement" | "change_cannot_be_established";
  caution: string;
}

export interface CompareDiagnosesResponse {
  a: DiagnosisResponse;
  b: DiagnosisResponse;
  comparison: ObservationComparison;
}

// ---------- Plant tracking ----------
export type GrowingEnvironment = "field" | "greenhouse" | "indoor" | "orchard" | "nursery" | "other";

export interface PlantProfile {
  id: string;
  name: string;
  crop_type?: string | null;
  variety?: string | null;
  planting_date?: string | null;
  location_label?: string | null;
  growing_environment?: GrowingEnvironment | null;
  notes?: string | null;
  archived: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  observation_count: number;
  last_observed_at?: string | null;
  last_decision_status?: DecisionStatus | null;
  last_predicted_label?: string | null;
  last_predicted_display_name?: string | null;
}

export interface PlantProfileInput {
  name?: string;
  crop_type?: string | null;
  variety?: string | null;
  planting_date?: string | null;
  location_label?: string | null;
  growing_environment?: GrowingEnvironment | null;
  notes?: string | null;
  archived?: boolean;
}

export interface PaginatedPlantsResponse {
  items: PlantProfile[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export type NoteType = "user_note" | "follow_up" | "treatment_applied" | "expert_feedback" | "correction" | "plant_link_change";

export interface ObservationNote {
  id: string;
  note_type: NoteType;
  body: string;
  data: Record<string, unknown>;
  author_is_owner: boolean;
  created_at?: string | null;
}

export interface MeasurementPoint {
  diagnosis_id: string;
  diagnosed_at: string;
  affected_area_pct: number;
  method?: string | null;
  model_version?: string | null;
  image_quality_status?: string | null;
}

export interface PlantTimelineResponse {
  plant: PlantProfile;
  entries: { observation: DiagnosisSummarySchema; notes: ObservationNote[]; treatment_summary?: string | null }[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  measurement_series: MeasurementPoint[];
  measurement_series_note?: "no_segmentation_measurements" | "mixed_measurement_methods" | null;
  observations_without_measurement: number;
}

// ---------- Model info ----------
export interface FollowUpQuestion {
  id: string;
  type: "single" | "multi";
  options: string[];
}

export interface ModelInfo {
  available: boolean;
  reason?: string;
  model_version?: string;
  architecture?: string;
  num_classes?: number;
  supported_classes?: string[];
  supported_plants?: string[];
  has_healthy_class?: boolean;
  thresholds?: DecisionThresholds;
  segmentation_available?: boolean;
  segmentation_model_version?: string | null;
  follow_up_questions: FollowUpQuestion[];
}

// ---------- Assistant ----------
export interface AssistantSource {
  id: string;
  document_id: string;
  title: string;
  organization: string;
  url?: string | null;
  source_type: string;
  language?: string | null;
  published_date?: string | null;
  revised_date?: string | null;
  section?: string | null;
  excerpt: string;
  score?: number | null;
}

export interface AssistantChatRequest {
  message: string;
  language: "en" | "ar";
  history: { role: "user" | "assistant"; content: string }[];
  diagnosis_id?: string | null;
  plant_profile_id?: string | null;
}

export interface AssistantChatResponse {
  mode: "llm" | "retrieval_only" | "no_sources";
  language: string;
  answer?: string | null;
  citations: string[];
  sources: AssistantSource[];
  evidence_sufficient: boolean;
  recommends_expert: boolean;
  notices: string[];
  context_used: {
    diagnosis_id?: string | null;
    plant_profile_id?: string | null;
    model_result: string[];
    user_observations: string[];
  };
}

export interface KnowledgeDocument {
  id: string;
  title: string;
  organization: string;
  source_url?: string | null;
  source_type: string;
  language: string;
  published_date?: string | null;
  revised_date?: string | null;
  retrieved_at?: string | null;
  crops: string[];
  diseases: string[];
  license_note?: string | null;
  chunk_count: number;
}

// ---------- Dashboard (common_schemas.py) ----------
export interface PalmDiseaseStats {
  total_palm_scans: number;
  red_palm_weevil_incidents: number;
}

export interface CommonDiseaseCount {
  name: string;
  count: number;
}

export interface MonthlyTrendPoint {
  month: string;
  scan_count: number;
}

export interface DashboardResponse {
  total_scans: number;
  healthy_count: number;
  diseased_count: number;
  uncertain_count?: number;
  confident_count?: number;
  palm_disease_stats: PalmDiseaseStats;
  most_common_diseases: CommonDiseaseCount[];
  monthly_trend: MonthlyTrendPoint[];
}

// ---------- Admin (common_schemas.py) ----------
export interface UserAdminSchema {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
}

export interface PaginatedUsersResponse {
  items: UserAdminSchema[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface UpdateUserRequest {
  role?: UserRole;
  is_active?: boolean;
}

// ---------- Knowledge Base (common_schemas.py) ----------
export type TreatmentCategory = "organic" | "chemical" | "biological";

export interface DiseaseCreateRequest {
  plant_canonical_name: string;
  name: string;
  disease_type?: string;
  description: string;
  symptoms: string[];
  causes: string[];
  transmission_method?: string;
  recovery_probability?: number;
  estimated_recovery_time?: string;
}

export interface DiseaseResponseSchema {
  id: string;
  plant_id: string;
  name: string;
  disease_type?: string | null;
  description: string;
  symptoms: string[];
  causes: string[];
  transmission_method?: string | null;
  recovery_probability?: number | null;
  estimated_recovery_time?: string | null;
  version: number;
}

export interface PaginatedDiseasesResponse {
  items: DiseaseResponseSchema[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface TreatmentCreateRequest {
  disease_id: string;
  category: TreatmentCategory;
  instructions: string;
  safety_notes?: string;
  source_citation?: string;
  authority_referral_only: boolean;
}

export interface TreatmentResponseSchema {
  id: string;
  disease_id: string;
  category: TreatmentCategory;
  instructions: string;
  safety_notes?: string | null;
  source_citation?: string | null;
  authority_referral_only: boolean;
  version: number;
}

// ---------- Weather (common_schemas.py) ----------
export interface WeatherResponseSchema {
  available: boolean;
  temperature_c?: number | null;
  humidity_pct?: number | null;
  wind_speed_kmh?: number | null;
  rain_probability_pct?: number | null;
  uv_index?: number | null;
  reason?: string | null;
}

// ---------- System ----------
export interface HealthResponse {
  status: string;
  database: string;
  cache: string;
  ai_service: string;
}
