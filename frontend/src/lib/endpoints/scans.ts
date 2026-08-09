import { request } from "@/lib/apiClient";
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
}

export const scansApi = {
  createScan: ({ image, latitude, longitude, attachLocation }: CreateScanParams) => {
    const formData = new FormData();
    formData.append("image", image);
    if (latitude !== undefined) formData.append("latitude", String(latitude));
    if (longitude !== undefined) formData.append("longitude", String(longitude));
    formData.append("attach_location", String(Boolean(attachLocation)));
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
};
