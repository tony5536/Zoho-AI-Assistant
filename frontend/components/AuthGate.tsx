"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  consumeOAuthCallbackFromUrl,
  resolveAuthStatus,
  type AuthCheckStatus,
} from "@/lib/auth-client";

function AuthLoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface">
      <div className="flex items-center gap-3 rounded-xl border border-surface-border bg-surface-raised px-5 py-4">
        <span
          className="h-4 w-4 animate-spin rounded-full border-2 border-neutral-600 border-t-white"
          aria-hidden
        />
        <p className="text-sm text-neutral-400">Checking sign-in…</p>
      </div>
    </div>
  );
}

/** Protects dashboard routes; redirects unauthenticated users to /login. */
export function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [status, setStatus] = useState<AuthCheckStatus>("loading");

  useEffect(() => {
    let cancelled = false;

    async function run() {
      const oauthResult = consumeOAuthCallbackFromUrl();
      if (oauthResult === "error") {
        router.replace("/login?auth=error");
        return;
      }

      const authenticated = await resolveAuthStatus();
      if (cancelled) return;

      if (!authenticated) {
        router.replace("/login");
        return;
      }

      setStatus("authenticated");
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (status === "loading") {
    return <AuthLoadingScreen />;
  }

  return <>{children}</>;
}
