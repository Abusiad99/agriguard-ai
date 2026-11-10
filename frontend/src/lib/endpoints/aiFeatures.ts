import { request } from "@/lib/apiClient";
import type {
  AreaDetail,
  AreaLookup,
  Assessment,
  CompareResult,
  MapLayer,
  ModelCard,
  OutbreakFilters,
  OutbreakReadiness,
  Paginated,
  PlantScan,
  PredictionResult,
  Reminder,
  TimelineEvent,
  TrackedPlant,
  TrackedPlantDetail,
  TreatmentCategoryRecorded,
  TreatmentRecord,
  TreatmentStage,
} from "@/types/aiFeatures";

export const modelsApi = {
  list: () => request<ModelCard[]>("/models"),
};

export interface TrackedPlantInput {
  name: string;
  crop?: string | null;
  species?: string | null;
  notes?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  initial_diagnosis_id?: string | null;
}

export interface TreatmentInput {
  name: string;
  category: TreatmentCategoryRecorded;
  applied_on: string;
  application_notes?: string | null;
  dosage_text?: string | null;
  documentation_ref?: string | null;
  follow_up_on?: string | null;
  user_notes?: string | null;
}

export const plantsApi = {
  list: (params: { status?: "active" | "archived"; page?: number; pageSize?: number } = {}) =>
    request<Paginated<TrackedPlant>>("/tracked-plants", {
      query: { status: params.status, page: params.page, page_size: params.pageSize },
    }),
  create: (body: TrackedPlantInput) => request<TrackedPlant>("/tracked-plants", { method: "POST", body }),
  get: (id: string) => request<TrackedPlantDetail>(`/tracked-plants/${id}`),
  update: (id: string, body: Partial<TrackedPlantInput> & { status?: "active" | "archived"; clear_location?: boolean }) =>
    request<TrackedPlant>(`/tracked-plants/${id}`, { method: "PATCH", body }),
  linkScan: (id: string, diagnosisId: string, treatmentStage: TreatmentStage = "unknown") =>
    request<PlantScan>(`/tracked-plants/${id}/scans`, {
      method: "POST",
      body: { diagnosis_id: diagnosisId, treatment_stage: treatmentStage },
    }),
  unlinkScan: (id: string, diagnosisId: string) =>
    request<void>(`/tracked-plants/${id}/scans/${diagnosisId}`, { method: "DELETE" }),
  compare: (id: string, first?: string, second?: string) =>
    request<CompareResult>(`/tracked-plants/${id}/compare`, { query: { first, second } }),
  reassess: (id: string) => request<Assessment>(`/tracked-plants/${id}/assessment`, { method: "POST" }),
  timeline: (id: string, page = 1) =>
    request<Paginated<TimelineEvent>>(`/tracked-plants/${id}/timeline`, { query: { page, page_size: 50 } }),
  addTreatment: (id: string, body: TreatmentInput) =>
    request<TreatmentRecord>(`/tracked-plants/${id}/treatments`, { method: "POST", body }),
  deleteTreatment: (id: string, treatmentId: string) =>
    request<void>(`/tracked-plants/${id}/treatments/${treatmentId}`, { method: "DELETE" }),
  addReminder: (id: string, body: { kind: Reminder["kind"]; due_on: string; note?: string | null }) =>
    request<Reminder>(`/tracked-plants/${id}/reminders`, { method: "POST", body }),
  setReminderStatus: (id: string, reminderId: string, status: Reminder["status"]) =>
    request<Reminder>(`/tracked-plants/${id}/reminders/${reminderId}`, { method: "PATCH", body: { status } }),
  myReminders: (state: "open" | "overdue" | "completed" | "all" = "open") =>
    request<Paginated<Reminder>>("/tracked-plants/reminders", { query: { state, page_size: 50 } }),
};

export interface MapQuery {
  crop?: string;
  disease?: string;
  dateFrom?: string;
  dateTo?: string;
  bbox?: string;
  horizonDays?: number;
}

export const outbreakApi = {
  readiness: () => request<OutbreakReadiness>("/outbreak/readiness"),
  filters: () => request<OutbreakFilters>("/outbreak/filters"),
  map: (q: MapQuery) =>
    request<MapLayer>("/outbreak/map", {
      query: {
        crop: q.crop,
        disease: q.disease,
        date_from: q.dateFrom,
        date_to: q.dateTo,
        bbox: q.bbox,
        horizon_days: q.horizonDays,
        page_size: 500,
      },
    }),
  lookup: (lat: number, lon: number) => request<AreaLookup>("/outbreak/areas/lookup", { query: { lat, lon } }),
  area: (areaId: string, crop?: string, disease?: string, dateFrom?: string) =>
    request<AreaDetail>(`/outbreak/areas/${areaId}`, { query: { crop, disease, date_from: dateFrom } }),
  predict: (body: {
    crop: string;
    disease: string;
    horizon_days: number;
    area_id?: string;
    latitude?: number;
    longitude?: number;
  }) => request<PredictionResult>("/outbreak/predictions", { method: "POST", body }),
};
