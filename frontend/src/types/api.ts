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

export type DiagnosisStatus = "completed" | "unrecognized_plant";

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
}

export interface UnrecognizedPlantResponse {
  diagnosis_id?: string | null;
  status: "unrecognized_plant";
  message: string;
}

export type ScanResponse = DiagnosisResponse | UnrecognizedPlantResponse;

export function isUnrecognizedPlant(r: ScanResponse): r is UnrecognizedPlantResponse {
  return r.status === "unrecognized_plant";
}

export interface DiagnosisSummarySchema {
  id: string;
  plant?: string | null;
  disease?: string | null;
  severity_level?: SeverityLevel | null;
  confidence_score: number;
  thumbnail_url?: string | null;
  diagnosed_at?: string | null;
}

export interface PaginatedDiagnosesResponse {
  items: DiagnosisSummarySchema[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface CompareDiagnosesResponse {
  a: DiagnosisResponse;
  b: DiagnosisResponse;
  delta: {
    confidence_change: number;
    severity_change: string | null;
  };
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
