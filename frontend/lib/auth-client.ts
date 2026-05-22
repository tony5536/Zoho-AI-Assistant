import { fetchAuthStatus, logoutUser } from "@/lib/api";
import { getUserId, hasAuthFlag, setAuthFlag } from "@/lib/user";

export type AuthCheckStatus = "loading" | "authenticated" | "unauthenticated";

/** Read OAuth callback params on the dashboard route and persist client auth state. */
export function consumeOAuthCallbackFromUrl(): "success" | "error" | null {
  if (typeof window === "undefined") return null;

  const params = new URLSearchParams(window.location.search);
  const authResult = params.get("auth");

  if (authResult === "success") {
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

  const userId = getUserId();
  const ok = await fetchAuthStatus(userId);
  if (!ok) {
    clearAuthFlag();
    return false;
  }
  return true;
}

/** Sign out on the server and clear all client auth/session state. */
export async function signOut(): Promise<void> {
  const userId = getUserId();
  try {
    await logoutUser(userId);
  } catch {
    // Still clear local state so the user is signed out in the UI.
  }
  if (typeof window !== "undefined") {
    sessionStorage.clear();
    localStorage.clear();
  }
}
