import { request } from "@/lib/apiClient";
import type {
  LoginRequest,
  LogoutRequest,
  RefreshRequest,
  RegisterRequest,
  RegisterResponse,
  TokenResponse,
} from "@/types/api";

export const authApi = {
  register: (body: RegisterRequest) => request<RegisterResponse>("/auth/register", { method: "POST", body }),

  login: (body: LoginRequest) => request<TokenResponse>("/auth/login", { method: "POST", body }),

  refresh: (body: RefreshRequest) => request<TokenResponse>("/auth/refresh", { method: "POST", body }),

  logout: (body: LogoutRequest) => request<void>("/auth/logout", { method: "POST", body }),
};
