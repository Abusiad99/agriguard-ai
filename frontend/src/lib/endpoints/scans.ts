import { request } from "@/lib/apiClient";
import type {
  CompareDiagnosesResponse,
  DecisionStatus,
  DiagnosisResponse,
  Differential,
  ModelInfo,
  NoteType,
  ObservationNote,
  PaginatedDiagnosesResponse,
  ScanResponse,
} from "@/types/api";

export interface CreateScanParams {
  image: File;
  latitude?: number;
  longitude?: number;
  attachLocation?: boolean;
  plantProfileId?: string;
  newPlantName?: string;
  note?: string;
}

export const scansApi = {
  createScan: ({ image, latitude, longitude, attachLocation, plantProfileId, newPlantName, note }: CreateScanParams) => {
    const formData = new FormData();
    formData.append("image", image);
    if (latitude !== undefined) formData.append("latitude", String(latitude));
    if (longitude !== undefined) formData.append("longitude", String(longitude));
    formData.append("attach_location", String(Boolean(attachLocation)));
    if (plantProfileId) formData.append("plant_profile_id", plantProfileId);
    if (newPlantName) formData.append("new_plant_name", newPlantName);
    if (note) formData.append("note", note);
    return request<ScanResponse>("/scans", { method: "POST", formData });
  },

  getDiagnosis: (diagnosisId: string) => request<DiagnosisResponse>(`/diagnoses/${diagnosisId}`),

  listDiagnoses: (params: {
    plant?: string;
    disease?: string;
    date_from?: string;
    date_to?: string;
    decision_status?: DecisionStatus;
    plant_profile_id?: string;
    unassigned?: boolean;
    page?: number;
    page_size?: number;
  }) => request<PaginatedDiagnosesResponse>("/diagnoses", { query: params }),

  compareDiagnoses: (a: string, b: string) =>
    request<CompareDiagnosesResponse>("/diagnoses/compare", { query: { a, b } }),

  listNotes: (diagnosisId: string) => request<ObservationNote[]>(`/diagnoses/${diagnosisId}/notes`),

  addNote: (diagnosisId: string, noteType: Exclude<NoteType, "follow_up" | "plant_link_change">, body: string) =>
    request<ObservationNote>(`/diagnoses/${diagnosisId}/notes`, { method: "POST", body: { note_type: noteType, body } }),

  submitFollowUp: (diagnosisId: string, answers: Record<string, string | string[]>) =>
    request<Differential>(`/diagnoses/${diagnosisId}/follow-up`, { method: "POST", body: { answers } }),

  assignPlant: (diagnosisId: string, plantProfileId: string | null) =>
    request<DiagnosisResponse>(`/diagnoses/${diagnosisId}/plant`, { method: "PUT", body: { plant_profile_id: plantProfileId } }),

  modelInfo: () => request<ModelInfo>("/model/info"),
};
