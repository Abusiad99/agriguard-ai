import { request, requestBlob } from "@/lib/apiClient";
import type { TreatmentStage } from "@/types/aiFeatures";
import type {
  CompareDiagnosesResponse,
  DiagnosisResponse,
  PaginatedDiagnosesResponse,
  ScanResponse,
} from "@/types/api";

export interface CreateScanParams {
  image: File;
  latitude?: number;
  longitude?: number;
  attachLocation?: boolean;
  /** Follow-up scan of a tracked plant (must be one of the caller's plants). */
  trackedPlantId?: string;
  treatmentStage?: TreatmentStage;
}

export const scansApi = {
  createScan: ({ image, latitude, longitude, attachLocation, trackedPlantId, treatmentStage }: CreateScanParams) => {
    const formData = new FormData();
    formData.append("image", image);
    if (latitude !== undefined) formData.append("latitude", String(latitude));
    if (longitude !== undefined) formData.append("longitude", String(longitude));
    formData.append("attach_location", String(Boolean(attachLocation)));
    if (trackedPlantId) formData.append("tracked_plant_id", trackedPlantId);
    if (treatmentStage) formData.append("treatment_stage", treatmentStage);
    return request<ScanResponse>("/scans", { method: "POST", formData });
  },

  getDiagnosis: (diagnosisId: string) => request<DiagnosisResponse>(`/diagnoses/${diagnosisId}`),

  listDiagnoses: (params: {
    plant?: string;
    disease?: string;
    date_from?: string;
    date_to?: string;
    page?: number;
    page_size?: number;
  }) => request<PaginatedDiagnosesResponse>("/diagnoses", { query: params }),

  compareDiagnoses: (a: string, b: string) =>
    request<CompareDiagnosesResponse>("/diagnoses/compare", { query: { a, b } }),

  /** Segmentation artifact (mask / overlay / contours) as a Blob. These files are
   * owner-only, so they are fetched with the auth header rather than via <img src>. */
  getSegmentationArtifact: (artifactUrl: string) => requestBlob(artifactUrl.replace(/^\/api\/v1/, "")),
};
