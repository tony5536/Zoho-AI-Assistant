"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { mockLogin } from "@/lib/api";
import { getZohoAuthRedirectUrl } from "@/lib/auth-url";
import { startNewSessionOnLogin } from "@/lib/session";
import { getUserId, setAuthFlag, setUserId } from "@/lib/user";

export function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [signingIn, setSigningIn] = useState(false);
  const [zohoLoading, setZohoLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (searchParams.get("reauth") === "1") {
      setError("Your Zoho session expired. Please reconnect.");
      window.history.replaceState({}, "", "/login");
      return;
    }
    if (searchParams.get("auth") === "error") {
      setError(
        "Zoho sign-in did not complete. Please try again — avoid refreshing during login."
      );
      window.history.replaceState({}, "", "/login");
    }
  }, [searchParams]);

  const handleSignIn = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSigningIn(true);
    try {
      const user = await mockLogin(username.trim(), password);
      setUserId(user.user_id);
      setAuthFlag();
      startNewSessionOnLogin();
      router.replace("/");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not sign in. Please try again.";
      setError(message);
    } finally {
      setSigningIn(false);
    }
  };

  const handleContinue = () => {
    setError(null);
    setZohoLoading(true);
    window.location.href = getZohoAuthRedirectUrl(getUserId());
  };

  const busy = signingIn || zohoLoading;

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-surface px-6 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8 flex justify-center">
          <div
            className="flex h-12 w-12 items-center justify-center rounded-xl border border-surface-border bg-black"
            aria-hidden
          >
            <span className="text-lg font-bold text-white">Z</span>
          </div>
        </div>

        <div className="rounded-2xl border border-surface-border bg-surface-raised px-8 py-10 shadow-[0_0_0_1px_rgba(255,255,255,0.03)]">
          <h1 className="text-center text-xl font-semibold tracking-tight text-white sm:text-2xl">
            Zoho Projects AI Assistant
          </h1>
          <p className="mt-3 text-center text-sm leading-relaxed text-neutral-400">
            Secure AI-powered workspace assistant
          </p>

          <form onSubmit={handleSignIn} className="mt-8 space-y-4">
            <div>
              <label
                htmlFor="username"
                className="mb-1.5 block text-xs font-medium text-neutral-400"
              >
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={busy}
                required
                className="w-full rounded-xl border border-surface-border bg-neutral-950 px-4 py-3 text-sm text-white placeholder:text-neutral-600 focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 disabled:opacity-70"
                placeholder="jamie.lee"
              />
            </div>
            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-xs font-medium text-neutral-400"
              >
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={busy}
                required
                className="w-full rounded-xl border border-surface-border bg-neutral-950 px-4 py-3 text-sm text-white placeholder:text-neutral-600 focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 disabled:opacity-70"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={busy}
              className="flex w-full items-center justify-center gap-2.5 rounded-xl bg-white px-4 py-3.5 text-sm font-semibold text-black transition-colors hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {signingIn ? (
                <>
                  <span
                    className="h-4 w-4 animate-spin rounded-full border-2 border-neutral-400 border-t-black"
                    aria-hidden
                  />
                  <span>Signing in…</span>
                </>
              ) : (
                "Sign In"
              )}
            </button>
          </form>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center" aria-hidden>
              <div className="w-full border-t border-surface-border" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-surface-raised px-2 text-neutral-500">or</span>
            </div>
          </div>

          <button
            type="button"
            onClick={handleContinue}
            disabled={busy}
            className="flex w-full items-center justify-center gap-2.5 rounded-xl border border-surface-border bg-neutral-950 px-4 py-3.5 text-sm font-semibold text-white transition-colors hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {zohoLoading ? (
              <>
                <span
                  className="h-4 w-4 animate-spin rounded-full border-2 border-neutral-600 border-t-white"
                  aria-hidden
                />
                <span>Redirecting…</span>
              </>
            ) : (
              "Continue with Zoho"
            )}
          </button>

          {error && (
            <p
              className="mt-4 rounded-lg border border-neutral-700 bg-neutral-900/80 px-3 py-2.5 text-center text-sm text-neutral-200"
              role="alert"
            >
              {error}
            </p>
          )}
        </div>

        <p className="mt-6 text-center text-xs text-neutral-600">
          Demo sign-in uses test accounts. Zoho OAuth is available for real project
          access.
        </p>
      </div>
    </div>
  );
}
