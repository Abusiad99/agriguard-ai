/**
 * Token storage. Access tokens live only in memory (never persisted — they're
 * short-lived, 15 min per backend/app/core/config.py's
 * access_token_expire_minutes) to reduce XSS exposure window. Refresh tokens are
 * persisted to localStorage so a page reload doesn't force a re-login, matching
 * the 30-day refresh_token_expire_days on the backend.
 */
const REFRESH_TOKEN_KEY = "agriguard_refresh_token";

let inMemoryAccessToken: string | null = null;

export const tokenStorage = {
  getAccessToken(): string | null {
    return inMemoryAccessToken;
  },
  setAccessToken(token: string | null): void {
    inMemoryAccessToken = token;
  },
  getRefreshToken(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  },
  setRefreshToken(token: string | null): void {
    if (token) {
      localStorage.setItem(REFRESH_TOKEN_KEY, token);
    } else {
      localStorage.removeItem(REFRESH_TOKEN_KEY);
    }
  },
  clear(): void {
    inMemoryAccessToken = null;
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};
