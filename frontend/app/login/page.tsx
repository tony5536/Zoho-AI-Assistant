import { Suspense } from "react";
import { LoginPage } from "@/components/LoginPage";

export const metadata = {
  title: "Sign in | Zoho Projects AI Assistant",
  description: "Sign in with Zoho to use the AI workspace assistant",
};

function LoginFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface">
      <p className="text-sm text-neutral-500">Loading…</p>
    </div>
  );
}

export default function LoginRoute() {
  return (
    <Suspense fallback={<LoginFallback />}>
      <LoginPage />
    </Suspense>
  );
}
