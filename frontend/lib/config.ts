const stripTrailingSlash = (url: string) => url.replace(/\/$/, "");

/**
 * Browser fetch base — same-origin `/api` proxied to FastAPI (no CORS).
 * Set in frontend/.env.local: NEXT_PUBLIC_API_URL=/api
 */
export const API_BASE = stripTrailingSlash(
  process.env.NEXT_PUBLIC_API_URL ?? "/api"
);

/**
 * Direct backend URL for OAuth browser redirects only (Zoho → :8000 callback).
 */
export const BACKEND_DIRECT_URL = stripTrailingSlash(
  process.env.NEXT_PUBLIC_BACKEND_DIRECT_URL ?? "http://localhost:8000"
);

export const HEALTH_URL = `${API_BASE}/health`;
