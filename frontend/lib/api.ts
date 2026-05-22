import { API_BASE, HEALTH_URL } from "@/lib/config";
import type {
  ChatRequest,
  ChatResponse,
  MemoryContextResponse,
  RecentSessionItem,
  SessionRestoreResponse,
} from "./types";

if (typeof window !== "undefined") {
  console.debug("[api] API base URL:", API_BASE);
  if (API_BASE.includes(":8000")) {
    console.error(
      "[api] Cross-origin API URL detected. Set NEXT_PUBLIC_API_URL=/api in frontend/.env.local and restart: npm run dev"
    );
  }
}

export type ApiConnectionIssue =
  | "backend_offline"
  | "cors"
  | "wrong_url"
  | "network"
  | "http_error";

export type ApiDiagnostics = {
  ok: boolean;
  issue?: ApiConnectionIssue;
  message: string;
  apiBase: string;
  status?: number;
};

const DEFAULT_RETRY_COUNT = 2;
const RETRY_DELAY_MS = 400;
export const REQUEST_TIMEOUT_MS = 90_000;
export const GENERIC_REQUEST_ERROR = "Something went wrong. Please retry.";

export type FetchOptions = {
  retries?: number;
  delayMs?: number;
  timeoutMs?: number;
  signal?: AbortSignal;
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function logDebug(message: string, extra?: Record<string, unknown>): void {
  if (typeof window !== "undefined") {
    console.debug(`[api] ${message}`, extra ?? "");
  }
}

function logWarn(message: string, extra?: Record<string, unknown>): void {
  if (typeof window !== "undefined") {
    console.warn(`[api] ${message}`, extra ?? "");
  }
}

function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === "AbortError") ||
    (err instanceof Error && err.name === "AbortError")
  );
}

/** Fetch with short retries for transient local dev network blips. */
export async function fetchWithRetry(
  url: string,
  init?: RequestInit,
  options?: FetchOptions
): Promise<Response> {
  const retries = options?.retries ?? DEFAULT_RETRY_COUNT;
  const delayMs = options?.delayMs ?? RETRY_DELAY_MS;
  const timeoutMs = options?.timeoutMs ?? REQUEST_TIMEOUT_MS;
  const externalSignal = options?.signal;
  let lastError: unknown;

  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController();
    const timer =
      timeoutMs > 0
        ? setTimeout(() => controller.abort(), timeoutMs)
        : null;

    if (externalSignal) {
      if (externalSignal.aborted) {
        if (timer) clearTimeout(timer);
        throw new DOMException("Aborted", "AbortError");
      }
      externalSignal.addEventListener(
        "abort",
        () => controller.abort(),
        { once: true }
      );
    }

    try {
      logDebug(`fetch attempt ${attempt + 1}/${retries + 1}`, {
        url,
        method: init?.method ?? "GET",
      });
      const res = await fetch(url, {
        ...init,
        signal: controller.signal,
      });
      logDebug("fetch response", { url, status: res.status, ok: res.ok });
      return res;
    } catch (err) {
      lastError = err;
      if (isAbortError(err)) {
        if (externalSignal?.aborted) {
          throw err;
        }
        lastError = new Error("Request timed out. Please try again.");
      }
      logWarn("fetch failed", {
        url,
        apiBase: API_BASE,
        attempt: attempt + 1,
        error: err instanceof Error ? err.message : String(err),
        name: err instanceof Error ? err.name : undefined,
      });
      if (isAbortError(err) && externalSignal?.aborted) {
        throw err;
      }
      if (attempt < retries) {
        await sleep(delayMs);
      }
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  throw lastError;
}

/** Probe GET /health before surfacing a connection error to the user. */
export async function checkApiHealth(): Promise<ApiDiagnostics> {
  logDebug("health check", { url: HEALTH_URL, apiBase: API_BASE });

  try {
    const res = await fetchWithRetry(
      HEALTH_URL,
      { method: "GET", cache: "no-store" },
      { retries: DEFAULT_RETRY_COUNT, delayMs: RETRY_DELAY_MS }
    );

    if (res.ok) {
      const data = (await res.json()) as { status?: string };
      if (data.status === "ok") {
        return { ok: true, message: "Backend is reachable.", apiBase: API_BASE, status: res.status };
      }
      return {
        ok: false,
        issue: "http_error",
        message: `Health endpoint returned unexpected data from ${HEALTH_URL}. Check NEXT_PUBLIC_API_URL.`,
        apiBase: API_BASE,
        status: res.status,
      };
    }

    if (res.status === 404) {
      return {
        ok: false,
        issue: "wrong_url",
        message: `No /health at ${API_BASE}. Wrong NEXT_PUBLIC_API_URL or backend not this app.`,
        apiBase: API_BASE,
        status: res.status,
      };
    }

    return {
      ok: false,
      issue: "http_error",
      message: `Backend at ${API_BASE} responded with HTTP ${res.status}.`,
      apiBase: API_BASE,
      status: res.status,
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const lower = message.toLowerCase();

    if (lower.includes("failed to fetch") || lower.includes("networkerror")) {
      const pageOrigin =
        typeof window !== "undefined" ? window.location.origin : "";
      const allowedOrigins = ["http://localhost:3000", "http://127.0.0.1:3000"];
      if (pageOrigin && !allowedOrigins.includes(pageOrigin)) {
        return {
          ok: false,
          issue: "wrong_url",
          message: `Frontend must run at http://localhost:3000 (current: ${pageOrigin}). Use: npm run dev`,
          apiBase: API_BASE,
        };
      }

      return {
        ok: false,
        issue: "backend_offline",
        message:
          `Cannot reach ${HEALTH_URL}. Start backend: uvicorn app.main:app --reload --port 8000. ` +
          `Then restart frontend: npm run dev (proxies /api → :8000).`,
        apiBase: API_BASE,
      };
    }

    return {
      ok: false,
      issue: "network",
      message: `Network error talking to ${API_BASE}: ${message}`,
      apiBase: API_BASE,
    };
  }
}

/** Build a user-facing error after /health and optional request failure. */
export async function diagnoseApiConnection(
  requestError?: unknown
): Promise<ApiDiagnostics> {
  const health = await checkApiHealth();
  if (health.ok) {
    const detail =
      requestError instanceof Error ? requestError.message : String(requestError ?? "");
    return {
      ok: false,
      issue: "network",
      message:
        `API proxy is up (${HEALTH_URL}) but the request failed (${detail || "Failed to fetch"}). ` +
        `Check the browser Network tab for the failing URL, restart both servers, and inspect backend logs.`,
      apiBase: API_BASE,
    };
  }
  return health;
}

async function throwConnectionError(cause?: unknown): Promise<never> {
  const diagnosis = await diagnoseApiConnection(cause);
  logWarn("connection error", { diagnosis, cause });
  throw new Error(GENERIC_REQUEST_ERROR);
}

export async function fetchAuthStatus(userId: string): Promise<boolean> {
  try {
    const res = await fetchWithRetry(
      `${API_BASE}/auth/status?user_id=${encodeURIComponent(userId)}`
    );
    if (!res.ok) {
      logDebug("auth status not ok", { status: res.status });
      return false;
    }
    const data = (await res.json()) as { authenticated: boolean };
    return data.authenticated;
  } catch (err) {
    logWarn("auth status unreachable", { error: err });
    return false;
  }
}

export async function logoutUser(userId: string): Promise<void> {
  const res = await fetchWithRetry(
    `${API_BASE}/auth/logout?user_id=${encodeURIComponent(userId)}`,
    { method: "POST" }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Could not sign out");
  }
}

export type MockLoginResponse = {
  user_id: string;
  username: string;
  display_name: string;
  welcome_message?: string | null;
  last_active_project?: { project_id: string; project_name: string } | null;
  frequent_project?: { project_id: string; project_name: string } | null;
  recent_queries?: string[];
};

export async function mockLogin(
  username: string,
  password: string
): Promise<MockLoginResponse> {
  let res: Response;
  try {
    res = await fetchWithRetry(`${API_BASE}/auth/mock-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
  } catch (err) {
    return await throwConnectionError(err);
  }

  if (res.status === 401) {
    throw new Error("Invalid username or password.");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Could not sign in");
  }
  return res.json() as Promise<MockLoginResponse>;
}

export async function startZohoLogin(userId: string): Promise<void> {
  let res: Response;
  try {
    res = await fetchWithRetry(
      `${API_BASE}/auth/login?user_id=${encodeURIComponent(userId)}`
    );
  } catch (err) {
    return await throwConnectionError(err);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Could not start Zoho login");
  }
  const data = (await res.json()) as { authorization_url: string };
  window.location.href = data.authorization_url;
}

export const ZOHO_SESSION_EXPIRED_MESSAGE =
  "Your Zoho session expired. Please reconnect.";

export class ZohoReauthError extends Error {
  readonly reauthRequired = true;

  constructor(message = ZOHO_SESSION_EXPIRED_MESSAGE) {
    super(message);
    this.name = "ZohoReauthError";
  }
}

/** Turn API error JSON into a short user-facing message. */
export function parseApiError(text: string, status?: number): string {
  if (status != null && status >= 500) {
    return GENERIC_REQUEST_ERROR;
  }
  try {
    const data = JSON.parse(text) as {
      reauth_required?: boolean;
      detail?: string;
    };
    if (data.reauth_required) {
      return ZOHO_SESSION_EXPIRED_MESSAGE;
    }
    if (data.detail && typeof data.detail === "string") {
      const detail = data.detail;
      if (
        detail.includes("Internal server error") ||
        detail.includes("Zoho Projects HTTP error") ||
        detail.startsWith("{")
      ) {
        return GENERIC_REQUEST_ERROR;
      }
      return detail;
    }
  } catch {
    // not JSON
  }
  if (text.length > 200 || text.includes("Traceback")) {
    return GENERIC_REQUEST_ERROR;
  }
  return text || GENERIC_REQUEST_ERROR;
}

/** Map any thrown fetch/chat error to an assistant-safe UI string. */
export function toUserFacingError(err: unknown): string {
  if (err instanceof ZohoReauthError) {
    return ZOHO_SESSION_EXPIRED_MESSAGE;
  }
  if (isAbortError(err)) {
    return GENERIC_REQUEST_ERROR;
  }
  if (err instanceof Error) {
    const msg = err.message;
    if (msg === ZOHO_SESSION_EXPIRED_MESSAGE) return msg;
    if (
      msg.includes("API proxy is up") ||
      msg.includes("Failed to fetch") ||
      msg.includes("Network error") ||
      msg.includes("Cannot reach") ||
      msg.includes("Internal server error") ||
      msg.startsWith("{")
    ) {
      return GENERIC_REQUEST_ERROR;
    }
    if (msg === GENERIC_REQUEST_ERROR || msg.includes("Request timed out")) {
      return GENERIC_REQUEST_ERROR;
    }
    return msg;
  }
  return GENERIC_REQUEST_ERROR;
}

function throwIfReauthRequired(text: string, status: number): void {
  if (status !== 401) return;
  try {
    const data = JSON.parse(text) as { reauth_required?: boolean };
    if (data.reauth_required) {
      throw new ZohoReauthError();
    }
  } catch (err) {
    if (err instanceof ZohoReauthError) throw err;
  }
}

export async function deleteConversation(
  userId: string,
  sessionId: string
): Promise<void> {
  const params = new URLSearchParams({ user_id: userId });
  let res: Response;
  try {
    res = await fetchWithRetry(
      `${API_BASE}/memory/sessions/${encodeURIComponent(sessionId)}?${params}`,
      { method: "DELETE" }
    );
  } catch (err) {
    return await throwConnectionError(err);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseApiError(text) || "Could not delete conversation");
  }
}

export async function deleteChatMessage(
  userId: string,
  messageId: number
): Promise<void> {
  const params = new URLSearchParams({ user_id: userId });
  let res: Response;
  try {
    res = await fetchWithRetry(
      `${API_BASE}/memory/messages/${messageId}?${params}`,
      { method: "DELETE" }
    );
  } catch (err) {
    return await throwConnectionError(err);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseApiError(text) || "Could not delete message");
  }
}

export async function fetchRecentSessions(
  userId: string
): Promise<RecentSessionItem[]> {
  const params = new URLSearchParams({ user_id: userId });
  let res: Response;
  try {
    res = await fetchWithRetry(`${API_BASE}/memory/recent-sessions?${params}`);
  } catch (err) {
    return await throwConnectionError(err);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Could not load recent sessions");
  }
  return res.json() as Promise<RecentSessionItem[]>;
}

export async function fetchSessionRestore(
  userId: string,
  sessionId?: string
): Promise<SessionRestoreResponse> {
  const params = new URLSearchParams({ user_id: userId });
  if (sessionId) {
    params.set("session_id", sessionId);
  }
  let res: Response;
  try {
    res = await fetchWithRetry(`${API_BASE}/memory/restore?${params}`);
  } catch (err) {
    return await throwConnectionError(err);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Could not restore session");
  }
  return res.json() as Promise<SessionRestoreResponse>;
}

export async function fetchMemoryContext(
  userId: string,
  sessionId: string
): Promise<MemoryContextResponse> {
  const params = new URLSearchParams({
    user_id: userId,
    session_id: sessionId,
  });
  let res: Response;
  try {
    res = await fetchWithRetry(`${API_BASE}/memory/context?${params}`);
  } catch (err) {
    return await throwConnectionError(err);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Could not load memory context");
  }
  return res.json() as Promise<MemoryContextResponse>;
}

export async function sendChatMessage(
  payload: ChatRequest,
  options?: { signal?: AbortSignal }
): Promise<ChatResponse> {
  const url = `${API_BASE}/chat`;

  let res: Response;
  try {
    res = await fetchWithRetry(
      url,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      {
        retries: DEFAULT_RETRY_COUNT,
        delayMs: RETRY_DELAY_MS,
        timeoutMs: REQUEST_TIMEOUT_MS,
        signal: options?.signal,
      }
    );
  } catch (err) {
    if (isAbortError(err) && options?.signal?.aborted) {
      throw err;
    }
    return await throwConnectionError(err);
  }

  if (!res.ok) {
    const text = await res.text();
    throwIfReauthRequired(text, res.status);
    throw new Error(parseApiError(text, res.status));
  }

  try {
    return (await res.json()) as ChatResponse;
  } catch {
    throw new Error(GENERIC_REQUEST_ERROR);
  }
}

/** Strip internal project-id prefixes from assistant replies for display. */
export function displayReply(reply: string): string {
  return reply.replace(/^\[(PRJ-\d+)\]\s*/, "");
}
