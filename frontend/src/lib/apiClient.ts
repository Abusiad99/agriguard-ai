/**
 * Core API client. Every endpoint module (lib/endpoints/*.ts) calls through this
 * single `request()` function, so auth-header injection, error-envelope parsing
 * (API spec §1.1), and automatic access-token refresh-on-401 are handled in exactly
 * one place.
 */
import { ApiError, type ApiErrorResponse, type TokenResponse } from "@/types/api";
import { tokenStorage } from "@/lib/tokenStorage";

const API_PREFIX = "/api/v1";

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  formData?: FormData;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  /** Internal: prevents infinite refresh loops when refresh itself fails. */
  _isRetry?: boolean;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(API_PREFIX + path, window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.pathname + url.search;
}

/** Error code for a response without the API's JSON error body - for example one produced
 * by a proxy in front of the backend - so the app can still say what happened. */
export function codeForStatus(status: number): string {
  if (status === 429) return "RATE_LIMITED";
  if (status === 413) return "FILE_TOO_LARGE";
  if (status === 502 || status === 503 || status === 504) return "SERVICE_UNAVAILABLE";
  return "UNKNOWN_ERROR";
}

/** ApiError for a failed response, from its JSON error body when it has a valid one. */
async function errorFromResponse(res: Response): Promise<ApiError> {
  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      const errorBody = (await res.json()) as ApiErrorResponse;
      if (errorBody && errorBody.error && typeof errorBody.error.code === "string") {
        return new ApiError(res.status, errorBody);
      }
    } catch {
      // Not valid JSON: fall through to the status-based error.
    }
  }
  return new ApiError(res.status, {
    error: { code: codeForStatus(res.status), message: res.statusText || "Request failed.", details: [] },
  });
}

let refreshInFlight: Promise<boolean> | null = null;

/** Attempts to refresh the access token using the stored refresh token.
 * Returns true on success. De-duplicates concurrent refresh attempts (e.g. several
 * components fetching at once) into a single in-flight request. */
async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = tokenStorage.getRefreshToken();
  if (!refreshToken) return false;

  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(API_PREFIX + "/auth/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!res.ok) return false;
        const data: TokenResponse = await res.json();
        tokenStorage.setAccessToken(data.access_token);
        tokenStorage.setRefreshToken(data.refresh_token);
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, formData, query, signal, _isRetry } = options;

  const headers: Record<string, string> = {};
  const accessToken = tokenStorage.getAccessToken();
  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  let requestBody: BodyInit | undefined;
  if (formData) {
    requestBody = formData; // browser sets multipart Content-Type + boundary automatically
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    requestBody = JSON.stringify(body);
  }

  const res = await fetch(buildUrl(path, query), {
    method,
    headers,
    body: requestBody,
    signal,
  });

  // Access token expired mid-session: try one silent refresh, then retry the
  // original request exactly once (NFR-SEC-3 token rotation).
  if (res.status === 401 && !_isRetry && path !== "/auth/refresh" && path !== "/auth/login") {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      return request<T>(path, { ...options, _isRetry: true });
    }
    tokenStorage.clear();
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const contentType = res.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");

  if (!res.ok) {
    throw await errorFromResponse(res);
  }

  if (isJson) {
    return (await res.json()) as T;
  }
  // Non-JSON success (e.g. PDF download handled separately via requestBlob).
  return undefined as T;
}

export async function requestBlob(path: string, query?: RequestOptions["query"]): Promise<Blob> {
  const headers: Record<string, string> = {};
  const accessToken = tokenStorage.getAccessToken();
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  let res = await fetch(buildUrl(path, query), { headers });
  if (res.status === 401) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      const retryHeaders: Record<string, string> = {
        Authorization: `Bearer ${tokenStorage.getAccessToken()}`,
      };
      res = await fetch(buildUrl(path, query), { headers: retryHeaders });
    }
  }
  if (!res.ok) {
    throw await errorFromResponse(res);
  }
  return res.blob();
}
