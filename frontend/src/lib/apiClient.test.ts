import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { codeForStatus, request } from "@/lib/apiClient";
import { ApiError } from "@/types/api";

// Error responses that do not come from the API itself (a proxy's HTML page, a broken body)
// must still turn into an error the app can explain: before this, a rate-limited sign-in
// through NGINX (plain-text 503) showed only "Something went wrong".

const respond = (status: number, body: string, contentType: string) =>
  vi.fn(async () => new Response(body, { status, headers: { "content-type": contentType } }));

async function failure(path: string): Promise<ApiError> {
  try {
    await request(path, { method: "POST", body: {} });
  } catch (err) {
    if (err instanceof ApiError) return err;
    throw err;
  }
  throw new Error("request did not fail");
}

describe("API client error handling", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { location: { origin: "https://demo.example" } });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("maps statuses without an API error body to specific codes", () => {
    expect(codeForStatus(429)).toBe("RATE_LIMITED");
    expect(codeForStatus(413)).toBe("FILE_TOO_LARGE");
    for (const s of [502, 503, 504]) expect(codeForStatus(s)).toBe("SERVICE_UNAVAILABLE");
    expect(codeForStatus(500)).toBe("UNKNOWN_ERROR");
  });

  it("explains a proxy's HTML rate-limit and outage pages", async () => {
    vi.stubGlobal("fetch", respond(429, "<html>429 Too Many Requests</html>", "text/html"));
    expect((await failure("/auth/login")).code).toBe("RATE_LIMITED");
    vi.stubGlobal("fetch", respond(503, "<html>503 Service Temporarily Unavailable</html>", "text/html"));
    expect((await failure("/auth/register")).code).toBe("SERVICE_UNAVAILABLE");
  });

  it("keeps the API's own error code and message", async () => {
    const body = JSON.stringify({ error: { code: "INVALID_CREDENTIALS", message: "Invalid email or password.", details: [] }, request_id: "r1" });
    vi.stubGlobal("fetch", respond(401, body, "application/json"));
    const err = await failure("/auth/login");
    expect(err.code).toBe("INVALID_CREDENTIALS");
    expect(err.message).toBe("Invalid email or password.");
    expect(err.status).toBe(401);
  });

  it("survives a JSON content type with a body that is not the API's error shape", async () => {
    vi.stubGlobal("fetch", respond(502, "not json", "application/json"));
    expect((await failure("/auth/login")).code).toBe("SERVICE_UNAVAILABLE");
    vi.stubGlobal("fetch", respond(429, '{"detail":"slow down"}', "application/json"));
    expect((await failure("/auth/login")).code).toBe("RATE_LIMITED");
  });
});
