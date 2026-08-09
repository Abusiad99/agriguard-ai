import { request } from "@/lib/apiClient";
import type {
  DiseaseCreateRequest,
  DiseaseResponseSchema,
  PaginatedDiseasesResponse,
  TreatmentCreateRequest,
  TreatmentResponseSchema,
} from "@/types/api";

export const diseasesApi = {
  list: (params: { plant_id?: string; search?: string; page?: number; page_size?: number }) =>
    request<PaginatedDiseasesResponse>("/diseases", { query: params }),

  create: (body: DiseaseCreateRequest) => request<DiseaseResponseSchema>("/diseases", { method: "POST", body }),

  update: (diseaseId: string, body: DiseaseCreateRequest) =>
    request<DiseaseResponseSchema>(`/diseases/${diseaseId}`, { method: "PUT", body }),
};

export const treatmentsApi = {
  listForDisease: (diseaseId: string) =>
    request<{ items: TreatmentResponseSchema[] }>("/treatments", { query: { disease_id: diseaseId } }),

  create: (body: TreatmentCreateRequest) =>
    request<TreatmentResponseSchema>("/treatments", { method: "POST", body }),

  update: (treatmentId: string, body: TreatmentCreateRequest) =>
    request<TreatmentResponseSchema>(`/treatments/${treatmentId}`, { method: "PUT", body }),
};
