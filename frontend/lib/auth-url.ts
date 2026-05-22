import { BACKEND_DIRECT_URL } from "@/lib/config";

/** Browser redirect target for Zoho OAuth (must be direct backend, not /api proxy). */
export function getZohoAuthRedirectUrl(userId?: string): string {
  const url = new URL(`${BACKEND_DIRECT_URL}/auth/zoho`);
  if (userId) {
    url.searchParams.set("state", userId);
  }
  return url.toString();
}
