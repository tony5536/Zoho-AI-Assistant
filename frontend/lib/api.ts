import type { ChatRequest, ChatResponse } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export async function fetchAuthStatus(userId: string): Promise<boolean> {
  const res = await fetch(
    `${API_BASE}/auth/status?user_id=${encodeURIComponent(userId)}`
  );
  if (!res.ok) return false;
  const data = (await res.json()) as { authenticated: boolean };
  return data.authenticated;
}

export async function logoutUser(userId: string): Promise<void> {
  const res = await fetch(
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
};

export async function mockLogin(
  username: string,
  password: string
): Promise<MockLoginResponse> {
  const res = await fetch(`${API_BASE}/auth/mock-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
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
  const res = await fetch(
    `${API_BASE}/auth/login?user_id=${encodeURIComponent(userId)}`
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Could not start Zoho login");
  }
  const data = (await res.json()) as { authorization_url: string };
  window.location.href = data.authorization_url;
}

export async function sendChatMessage(
  payload: ChatRequest
): Promise<ChatResponse> {
  const url = `${API_BASE}/chat`;

  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error(
      `Cannot reach the API at ${API_BASE}. Start the backend: uvicorn app.main:app --reload`
    );
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
