const SESSION_KEY = "zoho_assistant_session_id";
const FRESH_LOGIN_KEY = "zoho_assistant_fresh_login";

/** Accept UUIDs and legacy sess-* ids from localStorage. */
const SESSION_ID_RE = /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}|sess-[a-z0-9-]{8,120})$/i;

export function isValidSessionId(id: string): boolean {
  return SESSION_ID_RE.test(id.trim());
}

function generateId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `sess-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function getSessionId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem(SESSION_KEY);
  if (!id || !isValidSessionId(id)) {
    id = generateId();
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

/** Return a valid session id, replacing corrupted values in localStorage. */
export function ensureSessionId(): string {
  return getSessionId();
}

export function persistSessionId(id: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(SESSION_KEY, id);
}

export function resetSessionId(): string {
  const id = generateId();
  localStorage.setItem(SESSION_KEY, id);
  return id;
}

export function clearSessionId(): void {
  localStorage.removeItem(SESSION_KEY);
}

/** Fresh session id for a new login (does not restore prior chat). */
export function startNewSessionOnLogin(): string {
  if (typeof window !== "undefined") {
    sessionStorage.setItem(FRESH_LOGIN_KEY, "1");
  }
  return resetSessionId();
}

export function consumeFreshLoginFlag(): boolean {
  if (typeof window === "undefined") return false;
  const fresh = sessionStorage.getItem(FRESH_LOGIN_KEY) === "1";
  if (fresh) {
    sessionStorage.removeItem(FRESH_LOGIN_KEY);
  }
  return fresh;
}
