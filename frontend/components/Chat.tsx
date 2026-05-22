"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { signOut } from "@/lib/auth-client";
import { displayReply, fetchMemoryContext, sendChatMessage } from "@/lib/api";
import { getSessionId, resetSessionId } from "@/lib/session";
import { getUserId } from "@/lib/user";
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

const DEFAULT_WELCOME =
  "Hi — I can help with your Zoho projects: list projects and tasks, review team workload, and prepare create or delete actions for your approval.\n\nTry: \"What projects do I have?\" then \"Show tasks for the first one\".";

export function Chat() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState("");
  const [userId, setUserId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectContext, setProjectContext] = useState<ProjectContext | null>(
    null
  );
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(
    null
  );
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sid = getSessionId();
    const uidVal = getUserId();
    setSessionId(sid);
    setUserId(uidVal);

    let cancelled = false;
    (async () => {
      let welcome = DEFAULT_WELCOME;
      try {
        const ctx = await fetchMemoryContext(uidVal, sid);
        if (cancelled) return;
        if (ctx.welcome_message) {
          welcome = `${ctx.welcome_message}\n\n${DEFAULT_WELCOME}`;
        }
        if (ctx.project_context) {
          setProjectContext(ctx.project_context);
        }
      } catch {
        /* use default welcome when memory API is unavailable */
      }
      if (!cancelled) {
        setMessages([{ id: uid(), role: "assistant", content: welcome }]);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

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

  const handleLogout = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    setError(null);
    try {
      await signOut();
      router.replace("/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign out");
      setLoggingOut(false);
    }
  };

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
            <div className="ml-auto flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={handleNewSession}
                disabled={loggingOut}
                className="rounded-lg border border-surface-border px-3 py-1.5 text-xs font-medium text-neutral-400 transition-colors hover:border-neutral-500 hover:bg-neutral-900/60 hover:text-white disabled:opacity-50"
              >
                New session
              </button>
              <button
                type="button"
                onClick={handleLogout}
                disabled={loggingOut}
                aria-label="Sign out"
                className="flex items-center gap-1.5 rounded-lg border border-surface-border px-3 py-1.5 text-xs font-medium text-neutral-400 transition-colors hover:border-neutral-500 hover:bg-neutral-900/60 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loggingOut ? (
                  <>
                    <span
                      className="h-3 w-3 animate-spin rounded-full border-2 border-neutral-600 border-t-white"
                      aria-hidden
                    />
                    Signing out…
                  </>
                ) : (
                  "Logout"
                )}
              </button>
            </div>
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
