import { request, requestBlob } from "@/lib/apiClient";
import type { Paginated } from "@/types/aiFeatures";
import type { Report, ReportShare, ReportSummary, ReportType } from "@/types/reports";

export interface ReportRequest {
  type: ReportType;
  locale: "en" | "ar";
  subject_id?: string;
  crop?: string;
  disease?: string;
  latitude?: number;
  longitude?: number;
  date_from?: string;
  date_to?: string;
  horizon_days?: number;
}

export interface ReportListQuery {
  type?: ReportType;
  q?: string;
  dateFrom?: string;
  dateTo?: string;
  subjectId?: string;
  page?: number;
  pageSize?: number;
}

export const reportsApi = {
  create: (body: ReportRequest) => request<Report>("/agri-reports", { method: "POST", body }),
  list: (q: ReportListQuery = {}) =>
    request<Paginated<ReportSummary>>("/agri-reports", {
      query: { type: q.type, q: q.q, date_from: q.dateFrom, date_to: q.dateTo, subject_id: q.subjectId,
               page: q.page, page_size: q.pageSize },
    }),
  get: (id: string) => request<Report>(`/agri-reports/${id}`),
  versions: (id: string) => request<ReportSummary[]>(`/agri-reports/${id}/versions`),
  regenerate: (id: string, locale?: "en" | "ar") =>
    request<Report>(`/agri-reports/${id}/regenerate`, { method: "POST", body: { locale } }),
  pdf: (id: string) => requestBlob(`/agri-reports/${id}/pdf`),
  mapImage: (id: string) => requestBlob(`/agri-reports/${id}/map.png`),
  shares: (id: string) => request<ReportShare[]>(`/agri-reports/${id}/shares`),
  share: (id: string, expiresInDays: number) =>
    request<ReportShare>(`/agri-reports/${id}/shares`, { method: "POST", body: { expires_in_days: expiresInDays } }),
  revokeShare: (id: string, shareId: string) =>
    request<ReportShare>(`/agri-reports/${id}/shares/${shareId}`, { method: "DELETE" }),
  /** Public: anyone holding a valid share link. */
  shared: (token: string) => request<Report>(`/shared-reports/${token}`),
  sharedPdf: (token: string) => requestBlob(`/shared-reports/${token}/pdf`),
  sharedMapImage: (token: string) => requestBlob(`/shared-reports/${token}/map.png`),
};

/** Save a Blob as a file (PDF, PNG). */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
