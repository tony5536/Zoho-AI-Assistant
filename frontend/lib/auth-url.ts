const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

/** Browser redirect target for Zoho OAuth (backend `/auth/zoho`). */
export function getZohoAuthRedirectUrl(userId?: string): string {
  const url = new URL(`${API_BASE}/auth/zoho`);
  if (userId) {
    url.searchParams.set("state", userId);
  }
  return url.toString();
}
