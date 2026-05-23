import { fetchAuthStatus, logoutUser } from "@/lib/api";
import { isValidSessionId, persistSessionId } from "@/lib/session";
import {
  clearAuthFlag,
  getOAuthUserId,
  getStoredUserId,
  hasAuthFlag,
  OAUTH_USER_ID,
  setAuthFlag,
  setUserId,
} from "@/lib/user";

export type AuthCheckStatus = "loading" | "authenticated" | "unauthenticated";

/** Read OAuth callback params on the dashboard route and persist client auth state. */
export function consumeOAuthCallbackFromUrl(): "success" | "error" | null {
  if (typeof window === "undefined") return null;

  const params = new URLSearchParams(window.location.search);
  const authResult = params.get("auth");

  if (authResult === "success") {
    setUserId(getOAuthUserId());
    const urlSessionId = params.get("session_id")?.trim();
    if (urlSessionId && isValidSessionId(urlSessionId)) {
      persistSessionId(urlSessionId, OAUTH_USER_ID);
    }
    setAuthFlag();
  }

  if (
    authResult ||
    params.has("code") ||
    params.has("state") ||
    params.has("accounts-server")
  ) {
    window.history.replaceState({}, "", window.location.pathname);
  }

  if (authResult === "success") return "success";
  if (authResult === "error") return "error";
  return null;
}

/**
 * Resolve whether the user may access protected routes.
 * Uses sessionStorage for fast client state, then confirms with the backend.
 */
export async function resolveAuthStatus(): Promise<boolean> {
  if (!hasAuthFlag()) return false;

  const userId = getStoredUserId();
  if (!userId) {
    clearAuthFlag();
    return false;
  }
  const ok = await fetchAuthStatus(userId);
  if (!ok) {
    clearAuthFlag();
    return false;
  }
  return true;
}

/** Clear client auth after Zoho token revocation and send user to login. */
export function redirectToZohoReconnect(): void {
  if (typeof window === "undefined") return;
  clearAuthFlag();
  window.location.href = "/login?reauth=1";
}

/** Sign out on the server and clear auth only (preserve session restore linkage). */
export async function signOut(): Promise<void> {
  const userId = getStoredUserId();
  try {
    if (userId) {
      await logoutUser(userId);
    }
  } catch {
    // Still clear auth so the user is signed out in the UI.
  }
  clearAuthFlag();
}
