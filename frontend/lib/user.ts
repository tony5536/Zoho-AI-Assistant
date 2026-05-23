const USER_KEY = "zoho_assistant_user_id";

/** Canonical OAuth demo user (must match backend oauth_users). */
export const OAUTH_USER_ID = "tony-reno";

export const OAUTH_NEW_SESSION_MESSAGE =
  "New session started. Previous chats are preserved in memory.";

/** Canonical demo user ids (must match backend mock_users / mock_data seeds). */
export const MOCK_USER_IDS = new Set([
  "mock-jamie",
  "mock-alex",
  "mock-sam",
]);

/** Demo usernames and legacy ids → canonical mock user ids (matches backend seeds). */
const USERNAME_TO_CANONICAL: Record<string, string> = {
  "jamie.lee": "mock-jamie",
  "alex.morgan": "mock-alex",
  "sam.patel": "mock-sam",
};

export function isOAuthUserId(id: string): boolean {
  return id.trim() === OAUTH_USER_ID;
}

export function getOAuthUserId(): string {
  return OAUTH_USER_ID;
}

export function resolveMockUserId(userId: string): string {
  const trimmed = userId.trim();
  if (!trimmed) return trimmed;
  if (isOAuthUserId(trimmed)) return OAUTH_USER_ID;
  if (MOCK_USER_IDS.has(trimmed)) return trimmed;
  return USERNAME_TO_CANONICAL[trimmed] ?? trimmed;
}

function generateId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `user-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function isMockUserId(id: string): boolean {
  return MOCK_USER_IDS.has(id);
}

/** Read stored user id without creating a new anonymous id. */
export function getStoredUserId(): string {
  if (typeof window === "undefined") return "";
  const raw = localStorage.getItem(USER_KEY)?.trim() ?? "";
  return raw ? resolveMockUserId(raw) : "";
}

/** Stable id for OAuth (creates one only when none is stored yet). */
export function ensureUserId(): string {
  const stored = getStoredUserId();
  if (stored) return stored;
  const id = generateId();
  localStorage.setItem(USER_KEY, id);
  return id;
}

/** Prefer getStoredUserId; does not auto-create anonymous ids. */
export function getUserId(): string {
  return getStoredUserId();
}

export function setUserId(id: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(USER_KEY, resolveMockUserId(id));
}

export function clearAuthFlag(): void {
  sessionStorage.removeItem("zoho_auth_ok");
}

/** Remove all client-side user and auth state (call after server logout). */
export function clearUserData(): void {
  clearAuthFlag();
  localStorage.removeItem(USER_KEY);
}

export function setAuthFlag(): void {
  sessionStorage.setItem("zoho_auth_ok", "1");
}

export function hasAuthFlag(): boolean {
  return sessionStorage.getItem("zoho_auth_ok") === "1";
}

/** Persist demo/OAuth identity after successful sign-in. */
export function setAuthenticatedUser(userId: string): void {
  setUserId(userId);
  setAuthFlag();
}
