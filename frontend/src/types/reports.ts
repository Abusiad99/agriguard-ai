/**
 * Generated agricultural reports (schemas agriguard.report.v1 and v2). Source of truth:
 * backend/app/application/reporting/*. Labels and displayed values inside a report
 * are already in the report's own language; the UI only adds its own chrome.
 * v2 adds chapters, typed reasoning statements, references, recommendation horizons
 * and bases; every v2 field is optional here so v1 reports keep rendering.
 */
export type ReportType = "diagnosis" | "plant_progress" | "outbreak_area";

export type ProvenanceKind =
  | "model" | "model_evaluation" | "model_measurement" | "model_estimate" | "rule" | "sourced_rule" | "reference"
  | "knowledge_base" | "general_guidance" | "user_recorded" | "observation" | "historical" | "weather_provider"
  | "llm_summary" | "system";

export type StatementKind =
  | "measured" | "model" | "estimate" | "evaluation" | "knowledge" | "reference" | "rule" | "hypothesis" | "missing"
  | "observation";

export interface Provenance {
  kind: ProvenanceKind;
  source?: string;
  record?: string;
  version?: number | string;
  citation?: string;
}

export interface ReportFact {
  key: string;
  label: string;
  value: unknown;
  display: string;
  available: boolean;
  reason_code?: string;
  unit?: string;
  note?: string;
  lang?: string;
  refs?: string[];
  provenance: Provenance;
}

export interface ReportStatement {
  text: string;
  kind: StatementKind;
  provenance: Provenance;
  refs?: string[];
  evidence?: string[];
  lang?: string;
}

export interface ReportItem {
  text: string;
  when?: string;
  refs?: string[];
  kind?: string;
  provenance: Provenance;
}

export interface ReportMedia {
  id: string;
  kind: "photo" | "attention_heatmap" | "segmentation_overlay" | "segmentation_mask" | "segmentation_contours" | "region_map";
  url?: string | null;
  title?: string;
  caption?: string;
  explanation?: string;
  overlay_of?: string;
  generated?: boolean;
  refs?: string[];
  provenance: Provenance;
}

export interface ReportChart {
  id: string;
  kind: "line" | "bar" | "step";
  title: string;
  x: string[];
  series: { key: string; label: string; values: (number | null)[] }[];
  unit?: string;
  forecast_from?: number | null;
  markers?: { index: number; label: string; kind?: string }[];
  y_labels?: Record<string, string>;
  note?: string;
  provenance: Provenance;
}

export interface ReportSection {
  id: string;
  title: string;
  chapter?: string;
  facts: ReportFact[];
  rows?: { id: string; cells: ReportFact[] }[];
  text?: string;
  note?: string;
  refs?: string[];
  warning?: boolean;
  statements?: ReportStatement[];
  items?: ReportItem[];
  media_ids?: string[];
  chart_ids?: string[];
  events?: { date: string; display_date: string; event: string; label?: string }[];
  hypotheses?: { text: string; provenance: Provenance }[];
  map?: boolean;
}

export type Horizon = "immediate" | "short_term" | "long_term";
export type RecommendationBasis = "reference" | "knowledge_base" | "agriguard_rule" | "general_guidance";

export interface ReportRecommendation {
  id: string;
  rule: string;
  /** v1: action category; v2: action type tag (inspection, monitoring, …). */
  category: string;
  category_label: string;
  horizon?: Horizon;
  horizon_label?: string;
  basis?: RecommendationBasis;
  basis_label?: string;
  refs?: string[];
  general_practice?: boolean;
  priority: "high" | "medium" | "low";
  priority_label: string;
  title: string;
  reason: string;
  objective: string;
  timing: string;
  evidence: { key?: string; label?: string; display?: string }[];
  warnings: string[];
  provenance: Provenance;
  details?: {
    text?: string; lang?: string; citation?: string | null; verbatim_from_knowledge_base?: boolean;
    items?: { text: string; refs: string[]; basis: RecommendationBasis }[];
  };
}

export interface ReportReference {
  id: string;
  n: number;
  origin: "catalog" | "knowledge_base";
  title: string;
  authors?: string | null;
  organization?: string | null;
  url: string;
  doi?: string | null;
  publication_date?: string | null;
  source_type: string;
  source_type_label: string;
  language?: string | null;
  verified_on?: string | null;
  claims: string[];
}

export interface ReportContent {
  schema: string;
  generator: string;
  type: ReportType;
  locale: "en" | "ar";
  title: string;
  synthetic: boolean;
  subject: Record<string, unknown>;
  status: { code: string; label: string; level?: string | null; qualifier?: string; provenance: Provenance };
  key_facts: ReportFact[];
  sections: ReportSection[];
  media: ReportMedia[];
  charts: ReportChart[];
  recommendations: ReportRecommendation[];
  limitations: string[];
  methods: { id: string; name: string; kind: ProvenanceKind; version?: string | null; synthetic?: boolean }[];
  chapters?: { id: string; title: string }[];
  references?: ReportReference[];
  missing?: { key: string; label: string; reason: string; reason_code: string; section?: string }[];
  narrative: {
    source: "llm" | "template";
    model?: string | null;
    executive_summary: { text: string; fact_ids: string[] }[];
    recommendation_notes: { recommendation_id: string; text: string }[];
    facts: { id: string; key: string }[];
    validation: { passed: boolean; errors: string[]; llm_attempted: boolean };
  };
  map?: { selected: string; cells: { area: { id: string; grid_key: string; bounds: { south: number; west: number; north: number; east: number } };
    inspections?: number; positives?: number; prediction?: { risk_level: string } | null }[] };
}

export interface ReportSummary {
  id: string;
  reference: string;
  type: ReportType;
  version: number;
  title: string;
  locale: "en" | "ar";
  status: string | null;
  crop: string | null;
  disease: string | null;
  subject_id: string;
  narrative_source: "llm" | "template";
  synthetic: boolean;
  created_at: string | null;
}

export interface Report extends Omit<ReportSummary, "subject_id"> {
  subject_id?: string;
  generated_display: string;
  schema_version: string;
  generator_version: string;
  data_hash: string;
  narrative_model?: string | null;
  supersedes_id?: string | null;
  sources?: { kind: string; table: string; id: string; version?: number }[];
  share_expires_at?: string;
  content: ReportContent;
}

export interface ReportShare {
  id: string;
  created_at: string | null;
  expires_at: string;
  revoked_at: string | null;
  access_count: number;
  state: "active" | "expired" | "revoked";
  last_accessed_at: string | null;
  token?: string;
  path?: string;
}
