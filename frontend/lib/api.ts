import { API_BASE, HEALTH_URL } from "@/lib/config";
import type { ChatRequest, ChatResponse, MemoryContextResponse } from "./types";

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

/** Fetch with short retries for transient local dev network blips. */
export async function fetchWithRetry(
  url: string,
  init?: RequestInit,
  options?: { retries?: number; delayMs?: number }
): Promise<Response> {
  const retries = options?.retries ?? DEFAULT_RETRY_COUNT;
  const delayMs = options?.delayMs ?? RETRY_DELAY_MS;
  let lastError: unknown;

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      logDebug(`fetch attempt ${attempt + 1}/${retries + 1}`, { url, method: init?.method ?? "GET" });
      const res = await fetch(url, init);
      logDebug("fetch response", { url, status: res.status, ok: res.ok });
      return res;
    } catch (err) {
      lastError = err;
      logWarn("fetch failed", {
        url,
        apiBase: API_BASE,
        attempt: attempt + 1,
        error: err instanceof Error ? err.message : String(err),
        name: err instanceof Error ? err.name : undefined,
        cause:
          err instanceof Error && err.cause != null
            ? String(err.cause)
            : undefined,
        stack: err instanceof Error ? err.stack : undefined,
      });
      if (attempt < retries) {
        await sleep(delayMs);
      }
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
  throw new Error(diagnosis.message);
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
  payload: ChatRequest
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
      { retries: DEFAULT_RETRY_COUNT, delayMs: RETRY_DELAY_MS }
    );
  } catch (err) {
    return await throwConnectionError(err);
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed (${res.status})`);
  }

  return res.json() as Promise<ChatResponse>;
}

/** Strip internal project-id prefixes from assistant replies for display. */
export function displayReply(reply: string): string {
  return reply.replace(/^\[(PRJ-\d+)\]\s*/, "");
}
