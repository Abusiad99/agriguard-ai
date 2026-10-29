import { request } from "@/lib/apiClient";
import type {
  CompareDiagnosesResponse,
  DecisionStatus,
  PaginatedPlantsResponse,
  PlantProfile,
  PlantProfileInput,
  PlantTimelineResponse,
} from "@/types/api";

export const plantsApi = {
  list: (params: { search?: string; include_archived?: boolean; last_status?: DecisionStatus; page?: number; page_size?: number }) =>
    request<PaginatedPlantsResponse>("/plants", { query: params }),
  get: (id: string) => request<PlantProfile>(`/plants/${id}`),
  create: (input: PlantProfileInput) => request<PlantProfile>("/plants", { method: "POST", body: input }),
  update: (id: string, input: PlantProfileInput) => request<PlantProfile>(`/plants/${id}`, { method: "PATCH", body: input }),
  archive: (id: string) => request<void>(`/plants/${id}`, { method: "DELETE" }),
  timeline: (id: string, params: { date_from?: string; date_to?: string; decision_status?: DecisionStatus; page?: number; page_size?: number }) =>
    request<PlantTimelineResponse>(`/plants/${id}/timeline`, { query: params }),
  compare: (id: string, a: string, b: string) => request<CompareDiagnosesResponse>(`/plants/${id}/compare`, { query: { a, b } }),
};
