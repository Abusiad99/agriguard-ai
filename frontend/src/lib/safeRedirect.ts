/**
 * Where to go after signing in: only a path inside this app. The value comes from the
 * URL the visitor first opened, so anything that could make the router leave the site
 * ("//host", backslashes, encoded slashes or backslashes, control characters) falls back
 * to the dashboard. react-router 6.x has an open-redirect advisory for backslash paths
 * (GHSA-wrjc-x8rr-h8h6) that is only fixed in 7.18, so the check lives here.
 */
export function safeRedirectPath(path: unknown, fallback = "/dashboard"): string {
  if (typeof path !== "string" || !path.startsWith("/") || path.startsWith("//")) return fallback;
  // eslint-disable-next-line no-control-regex
  if (/[\\\u0000-\u001f\u007f]/.test(path) || /%(5c|2f|00)/i.test(path)) return fallback;
  return path;
}
