import { getUserId } from "@/lib/user";

const SESSION_KEY = "zoho_assistant_session_id";
const USER_SESSIONS_KEY = "zoho_assistant_user_sessions";

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

function readUserSessionMap(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(USER_SESSIONS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return {};
    return parsed as Record<string, string>;
  } catch {
    return {};
  }
}

/** Last active session id for a user (survives logout). */
export function getLinkedSessionId(userId: string): string | null {
  if (!userId) return null;
  const linked = readUserSessionMap()[userId];
  return linked && isValidSessionId(linked) ? linked : null;
}

export function linkSessionToUser(userId: string, sessionId: string): void {
  if (typeof window === "undefined" || !userId || !isValidSessionId(sessionId)) return;
  const map = readUserSessionMap();
  map[userId] = sessionId;
  localStorage.setItem(USER_SESSIONS_KEY, JSON.stringify(map));
}

export function persistSessionId(id: string, userId?: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(SESSION_KEY, id);
  const uid = userId || getUserId();
  if (uid) linkSessionToUser(uid, id);
}

export function resetSessionId(userId?: string): string {
  const id = generateId();
  persistSessionId(id, userId);
  return id;
}

export function clearSessionId(): void {
  localStorage.removeItem(SESSION_KEY);
}

