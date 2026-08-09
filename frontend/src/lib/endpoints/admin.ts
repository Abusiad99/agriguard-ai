import { request, requestBlob } from "@/lib/apiClient";
import type { PaginatedUsersResponse, UpdateUserRequest, UserAdminSchema } from "@/types/api";

export const adminApi = {
  listUsers: (params: {
    role?: string;
    is_active?: boolean;
    search?: string;
    page?: number;
    page_size?: number;
  }) => request<PaginatedUsersResponse>("/admin/users", { query: params }),

  updateUser: (userId: string, body: UpdateUserRequest) =>
    request<UserAdminSchema>(`/admin/users/${userId}`, { method: "PATCH", body }),

  /** Downloads the system-wide CSV export as an authenticated Blob (a plain <a
   * href> would not carry the JWT bearer token, since this endpoint requires
   * admin auth — see backend/app/interface/api/v1/admin_router.py). */
  exportReportsCsv: (dateFrom?: string, dateTo?: string) =>
    requestBlob("/admin/reports/export", { format: "csv", date_from: dateFrom, date_to: dateTo }),
};
