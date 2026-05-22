"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  displayReply,
  fetchAuthStatus,
  sendChatMessage,
  startZohoLogin,
} from "@/lib/api";
import { getSessionId, resetSessionId } from "@/lib/session";
import {
  getUserId,
  hasAuthFlag,
  setAuthFlag,
} from "@/lib/user";
import type {
  ChatMessage,
  ChatResponse,
  PendingAction,
  ProjectContext,
} from "@/lib/types";

function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

const ACTION_LABELS: Record<PendingAction["tool"], string> = {
  create_task: "Create task",
  update_task: "Update task",
  delete_task: "Delete task",
};

const WELCOME =
  "Hi — I can help with your Zoho projects: list projects and tasks, review team workload, and prepare create or delete actions for your approval.\n\nTry: \"What projects do I have?\" then \"Show tasks for the first one\".";

export function Chat() {
  const [sessionId, setSessionId] = useState("");
  const [userId, setUserId] = useState("");
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectContext, setProjectContext] = useState<ProjectContext | null>(
    null
  );
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(
    null
  );
  const bottomRef = useRef<HTMLDivElement>(null);

  const checkAuth = useCallback(async (userId: string) => {
    const ok = await fetchAuthStatus(userId);
    setAuthenticated(ok);
    if (ok) setAuthFlag();
  }, []);

  useEffect(() => {
    const sid = getSessionId();
    const initialUserId = getUserId();
    setSessionId(sid);
    setUserId(initialUserId);

    const params = new URLSearchParams(window.location.search);
    const authResult = params.get("auth");
    if (authResult === "success") {
      setAuthFlag();
    } else if (authResult === "error") {
      setError(
        "Zoho sign-in did not complete. Please connect again — do not refresh the login page."
      );
      setAuthenticated(false);
    }
    if (
      authResult ||
      params.has("code") ||
      params.has("state") ||
      params.has("accounts-server")
    ) {
      window.history.replaceState({}, "", window.location.pathname);
    }

    if (hasAuthFlag()) {
      setAuthenticated(true);
      checkAuth(initialUserId).catch(() => setAuthenticated(false));
    } else {
      checkAuth(initialUserId);
    }

    setMessages([{ id: uid(), role: "assistant", content: WELCOME }]);
  }, [checkAuth]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, pendingAction]);

  const applyResponse = useCallback((response: ChatResponse) => {
    setProjectContext(response.project_context ?? null);
    setPendingAction(
      response.requires_confirmation ? response.pending_action ?? null : null
    );
    setError(null);

    setMessages((prev) => [
      ...prev,
      {
        id: uid(),
        role: "assistant",
        content: displayReply(response.reply),
        status: response.status,
      },
    ]);
  }, []);

  const postMessage = useCallback(
    async (body: {
      message: string;
      confirm?: boolean;
      cancel?: boolean;
      action_id?: string;
    }) => {
      if (!sessionId || !userId) return;
      setError(null);
      setLoading(true);

      try {
        const response = await sendChatMessage({
          message: body.message,
          session_id: sessionId,
          user_id: userId,
          confirm: body.confirm ?? false,
          cancel: body.cancel ?? false,
          action_id: body.action_id ?? null,
        });
        applyResponse(response);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Something went wrong";
        setError(msg);
      } finally {
        setLoading(false);
      }
    },
    [sessionId, userId, applyResponse]
  );

  const handleSend = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [
      ...prev,
      { id: uid(), role: "user", content: text },
    ]);
    setInput("");
    await postMessage({ message: text });
  };

  const handleConfirm = async () => {
    if (!pendingAction || loading) return;
    setMessages((prev) => [
      ...prev,
      { id: uid(), role: "user", content: "Confirmed" },
    ]);
    await postMessage({
      message: "confirm",
      confirm: true,
      action_id: pendingAction.action_id,
    });
  };

  const handleCancel = async () => {
    if (loading) return;
    setPendingAction(null);
    await postMessage({ message: "cancel", cancel: true });
  };

  const handleNewSession = () => {
    const id = resetSessionId();
    setSessionId(id);
    setMessages([
      {
        id: uid(),
        role: "assistant",
        content: "New session started. How can I help with your projects?",
      },
    ]);
    setProjectContext(null);
    setPendingAction(null);
    setError(null);
  };

  const handleLogin = async () => {
    setError(null);
    try {
      await startZohoLogin(userId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  };

  if (authenticated === null) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface text-neutral-400">
        Checking sign-in…
      </div>
    );
  }

  if (!authenticated) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-surface px-6">
        <div className="w-full max-w-sm border border-surface-border bg-surface-raised p-8 text-center">
          <h1 className="text-lg font-semibold text-white">
            Zoho Projects Assistant
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-neutral-400">
            Connect your Zoho account to list projects, manage tasks, and review
            team utilisation.
          </p>
          <button
            type="button"
            onClick={handleLogin}
            className="mt-6 w-full rounded-lg bg-white px-4 py-3 text-sm font-semibold text-black hover:bg-neutral-200"
          >
            Connect Zoho
          </button>
          {error && (
            <p className="mt-4 text-sm text-neutral-300" role="alert">
              {error}
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell flex h-screen flex-col">
      <header className="shrink-0 border-b border-surface-border bg-surface-raised">
        <div className="mx-auto flex max-w-2xl flex-col gap-3 px-4 py-3.5 sm:px-5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <div
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-surface-border bg-black"
                aria-hidden
              >
                <span className="text-sm font-bold text-white">Z</span>
              </div>
              <div className="min-w-0">
                <h1 className="truncate text-sm font-semibold text-white">
                  Zoho Projects Assistant
                </h1>
                <p className="text-xs text-neutral-500">Signed in</p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleNewSession}
              className="shrink-0 rounded-lg border border-surface-border px-3 py-1.5 text-xs font-medium text-neutral-400 transition-colors hover:border-neutral-500 hover:text-white"
            >
              New session
            </button>
          </div>
          <ProjectBadge context={projectContext} />
        </div>
      </header>

      <main className="flex min-h-0 flex-1 flex-col">
        <div className="messages-scroll mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 overflow-y-auto px-4 py-8 sm:px-5">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          {loading && <LoadingBubble />}
          <div ref={bottomRef} className="h-2 shrink-0" />
        </div>

        <div className="shrink-0 border-t border-surface-border bg-surface-raised">
          <div className="mx-auto max-w-2xl px-4 py-3 sm:px-5">
            {error && (
              <p
                className="mb-3 rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-2.5 text-sm text-neutral-100"
                role="alert"
              >
                {error}
              </p>
            )}

            {pendingAction && (
              <ConfirmationCard
                action={pendingAction}
                loading={loading}
                onConfirm={handleConfirm}
                onCancel={handleCancel}
              />
            )}

            <form onSubmit={handleSend} className="flex gap-2.5">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  pendingAction
                    ? "Or type a new message…"
                    : "Message your assistant…"
                }
                disabled={loading}
                className="min-w-0 flex-1 rounded-xl border border-surface-border bg-black px-4 py-3 text-[15px] leading-snug text-neutral-100 placeholder:text-neutral-600 focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="shrink-0 rounded-xl bg-white px-5 py-3 text-sm font-semibold text-black transition-colors hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Send
              </button>
            </form>
          </div>
        </div>
      </main>
    </div>
  );
}

function ProjectBadge({ context }: { context: ProjectContext | null }) {
  if (context) {
    return (
      <div className="flex items-center gap-2.5 rounded-lg border border-neutral-600 bg-neutral-900/50 px-3 py-2">
        <span className="h-2 w-2 shrink-0 rounded-full bg-white" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-medium uppercase tracking-widest text-neutral-500">
            Active project
          </p>
          <p className="truncate text-sm text-neutral-100">{context.project_name}</p>
        </div>
        <span className="shrink-0 text-xs text-neutral-500">{context.project_id}</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-dashed border-surface-border px-3 py-2">
      <span className="h-2 w-2 shrink-0 rounded-full bg-neutral-600" aria-hidden />
      <p className="text-sm text-neutral-500">
        No project selected — e.g. &quot;use project PRJ-001&quot;
      </p>
    </div>
  );
}

function ConfirmationCard({
  action,
  loading,
  onConfirm,
  onCancel,
}: {
  action: PendingAction;
  loading: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const label = ACTION_LABELS[action.tool];

  return (
    <div
      className="mb-3 rounded-xl border border-neutral-600 bg-neutral-900 p-4"
      role="dialog"
      aria-label="Confirm action"
    >
      <p className="text-xs font-medium uppercase tracking-wider text-neutral-400">
        Approval required
      </p>
      <p className="mt-1 text-sm font-medium text-white">{label}</p>
      <p className="mt-2 text-sm leading-relaxed text-neutral-300">
        {action.summary}
      </p>
      <div className="mt-4 flex gap-2">
        <button
          type="button"
          onClick={onConfirm}
          disabled={loading}
          className="rounded-lg bg-white px-4 py-2 text-sm font-semibold text-black hover:bg-neutral-200 disabled:opacity-50"
        >
          Confirm
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={loading}
          className="rounded-lg border border-surface-border px-4 py-2 text-sm text-neutral-300 hover:border-neutral-500 hover:text-white disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function LoadingBubble() {
  return (
    <div className="flex gap-3">
      <AssistantAvatar />
      <div className="space-y-1.5">
        <p className="text-[11px] font-medium uppercase tracking-wider text-neutral-500">
          Assistant
        </p>
        <div className="flex items-center gap-3 rounded-2xl border border-surface-border bg-surface-raised px-4 py-3">
          <div className="loading-dots flex gap-1" aria-hidden>
            <span className="h-1.5 w-1.5 rounded-full bg-neutral-400" />
            <span className="h-1.5 w-1.5 rounded-full bg-neutral-400" />
            <span className="h-1.5 w-1.5 rounded-full bg-neutral-400" />
          </div>
          <span className="text-sm text-neutral-500">Thinking…</span>
        </div>
      </div>
    </div>
  );
}

function AssistantAvatar() {
  return (
    <div
      className="mt-5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-surface-border bg-neutral-900 text-xs font-semibold text-white"
      aria-hidden
    >
      AI
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "status") {
    return (
      <p className="text-center text-xs text-neutral-600">{message.content}</p>
    );
  }

  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex flex-col items-end gap-1.5">
        <span className="pr-1 text-[11px] font-medium uppercase tracking-wider text-neutral-500">
          You
        </span>
        <div className="max-w-[90%] rounded-2xl rounded-br-md border border-neutral-700 bg-neutral-800 px-4 py-3 text-[15px] leading-relaxed text-neutral-100 sm:max-w-[85%]">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <AssistantAvatar />
      <div className="min-w-0 flex-1 space-y-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wider text-neutral-500">
          Assistant
        </span>
        <div
          className={`max-w-full rounded-2xl rounded-bl-md border px-4 py-3 text-[15px] leading-relaxed sm:max-w-[95%] ${
            message.status === "error"
              ? "border-neutral-600 bg-neutral-900 text-neutral-100"
              : message.status === "confirmation_required"
                ? "border-neutral-500 bg-neutral-900 text-neutral-100"
                : "border-surface-border bg-surface-raised text-neutral-200"
          }`}
        >
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    </div>
  );
}
