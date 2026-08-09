import { request, requestBlob } from "@/lib/apiClient";
import type { DashboardResponse } from "@/types/api";

export const dashboardApi = {
  getMyDashboard: () => request<DashboardResponse>("/dashboard/me"),
  getSystemDashboard: () => request<DashboardResponse>("/dashboard/system"),
};

export const reportsApi = {
  /** Downloads the PDF report and returns a Blob the caller can turn into an
   * object URL for opening/saving (FR-REPORT-2). */
  downloadReport: (diagnosisId: string) => requestBlob(`/reports/${diagnosisId}`),
};

export const weatherApi = {
  getConditions: (lat: number, lon: number) =>
    request<import("@/types/api").WeatherResponseSchema>("/weather", { query: { lat, lon } }),
};
