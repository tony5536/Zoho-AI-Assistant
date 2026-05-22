const USER_KEY = "zoho_assistant_user_id";

function generateId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `user-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function getUserId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem(USER_KEY);
  if (!id) {
    id = generateId();
    localStorage.setItem(USER_KEY, id);
  }
  return id;
}

export function setUserId(id: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(USER_KEY, id);
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
