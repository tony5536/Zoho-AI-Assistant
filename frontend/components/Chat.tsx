"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { redirectToZohoReconnect, signOut } from "@/lib/auth-client";
import {
  deleteChatMessage,
  deleteConversation,
  displayReply,
  fetchRecentSessions,
  fetchSessionRestore,
  sendChatMessage,
  toUserFacingError,
  ZohoReauthError,
  ZOHO_SESSION_EXPIRED_MESSAGE,
} from "@/lib/api";
import {
  consumeFreshLoginFlag,
  ensureSessionId,
  persistSessionId,
  resetSessionId,
} from "@/lib/session";
import { getUserId } from "@/lib/user";
import type {
  ChatMessage,
  ChatResponse,
  PendingAction,
  ProjectContext,
  RecentSessionItem,
  SessionRestoreResponse,
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
  const [recentSessions, setRecentSessions] = useState<RecentSessionItem[]>(
    []
  );
  const [restoringSession, setRestoringSession] = useState(false);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(
    null
  );
  const bottomRef = useRef<HTMLDivElement>(null);
  const chatRequestSeqRef = useRef(0);
  const chatAbortRef = useRef<AbortController | null>(null);
  const restoreAbortRef = useRef<AbortController | null>(null);

  const cancelInFlightChat = useCallback(() => {
    chatRequestSeqRef.current += 1;
    chatAbortRef.current?.abort();
    chatAbortRef.current = null;
  }, []);

  const buildMessagesFromRestore = useCallback(
    (restore: SessionRestoreResponse): ChatMessage[] => {
      const history: ChatMessage[] = restore.messages.map((m) => ({
        id: uid(),
        dbId: m.id ?? null,
        role: m.role as ChatMessage["role"],
        content:
          m.role === "assistant" ? displayReply(m.content) : m.content,
      }));

      if (restore.restored && restore.restore_message) {
        return [
          {
            id: uid(),
            role: "assistant",
            content: restore.restore_message,
          },
          ...history,
        ];
      }
      if (history.length > 0) {
        return history;
      }
      return [{ id: uid(), role: "assistant", content: DEFAULT_WELCOME }];
    },
    []
  );

  const applySessionRestore = useCallback(
    (restore: SessionRestoreResponse, fallbackSessionId: string) => {
      const resolvedSid = restore.session_id ?? fallbackSessionId;
      persistSessionId(resolvedSid);
      setSessionId(resolvedSid);
      setProjectContext(restore.project_context ?? null);
      setPendingAction(null);
      setMessages(buildMessagesFromRestore(restore));
    },
    [buildMessagesFromRestore]
  );

  const loadRecentSessions = useCallback(async (uidVal: string) => {
    try {
      const sessions = await fetchRecentSessions(uidVal);
      setRecentSessions(sessions);
    } catch {
      setRecentSessions([]);
    }
  }, []);

  useEffect(() => {
    const sid = ensureSessionId();
    const uidVal = getUserId();
    setSessionId(sid);
    setUserId(uidVal);

    let cancelled = false;
    restoreAbortRef.current?.abort();
    const restoreController = new AbortController();
    restoreAbortRef.current = restoreController;

    (async () => {
      void loadRecentSessions(uidVal);
      if (consumeFreshLoginFlag()) {
        if (!cancelled) {
          setMessages([
            { id: uid(), role: "assistant", content: DEFAULT_WELCOME },
          ]);
          setProjectContext(null);
          setPendingAction(null);
        }
        return;
      }
      try {
        const restore = await fetchSessionRestore(uidVal, sid);
        if (cancelled || restoreController.signal.aborted) return;
        applySessionRestore(restore, sid);
      } catch {
        if (!cancelled && !restoreController.signal.aborted) {
          setMessages([
            { id: uid(), role: "assistant", content: DEFAULT_WELCOME },
          ]);
        }
      }
    })();

    return () => {
      cancelled = true;
      restoreController.abort();
    };
  }, [applySessionRestore, loadRecentSessions]);

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
      const activeSessionId = ensureSessionId();
      if (!activeSessionId || !userId) return;
      if (activeSessionId !== sessionId) {
        setSessionId(activeSessionId);
      }

      const requestId = ++chatRequestSeqRef.current;
      chatAbortRef.current?.abort();
      const controller = new AbortController();
      chatAbortRef.current = controller;

      setError(null);
      setLoading(true);

      try {
        const response = await sendChatMessage(
          {
            message: body.message,
            session_id: activeSessionId,
            user_id: userId,
            confirm: body.confirm ?? false,
            cancel: body.cancel ?? false,
            action_id: body.action_id ?? null,
          },
          { signal: controller.signal }
        );
        if (
          requestId !== chatRequestSeqRef.current ||
          controller.signal.aborted
        ) {
          return;
        }
        applyResponse(response);
        void loadRecentSessions(userId);
      } catch (err) {
        if (controller.signal.aborted || requestId !== chatRequestSeqRef.current) {
          return;
        }
        if (err instanceof ZohoReauthError) {
          setError(ZOHO_SESSION_EXPIRED_MESSAGE);
          redirectToZohoReconnect();
          return;
        }
        setError(toUserFacingError(err));
      } finally {
        if (requestId === chatRequestSeqRef.current) {
          setLoading(false);
          chatAbortRef.current = null;
        }
      }
    },
    [sessionId, userId, applyResponse, loadRecentSessions]
  );

  const handleSend = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const text = input.trim();
    if (!text || loading || restoringSession) return;

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
    cancelInFlightChat();
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

  const handleDeleteMessage = async (message: ChatMessage) => {
    setMessages((prev) => prev.filter((m) => m.id !== message.id));
    if (message.dbId != null && userId) {
      try {
        await deleteChatMessage(userId, message.dbId);
      } catch (err) {
        setError(toUserFacingError(err));
      }
    }
  };

  const handleDeleteRecentSession = async (
    targetSessionId: string,
    e: React.MouseEvent
  ) => {
    e.stopPropagation();
    if (!userId || deletingSessionId) return;
    setDeletingSessionId(targetSessionId);
    setError(null);
    try {
      await deleteConversation(userId, targetSessionId);
      setRecentSessions((prev) =>
        prev.filter((s) => s.session_id !== targetSessionId)
      );
      if (targetSessionId === sessionId) {
        handleNewSession();
      }
    } catch (err) {
      setError(toUserFacingError(err));
    } finally {
      setDeletingSessionId(null);
    }
  };

  const handleSelectRecent = async (targetSessionId: string) => {
    if (!userId || targetSessionId === sessionId || restoringSession) return;
    cancelInFlightChat();
    setRestoringSession(true);
    setError(null);
    try {
      const restore = await fetchSessionRestore(userId, targetSessionId);
      applySessionRestore(restore, targetSessionId);
    } catch (err) {
      setError(toUserFacingError(err));
    } finally {
      setRestoringSession(false);
    }
  };

  const handleLogout = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    setError(null);
    try {
      await signOut();
      router.replace("/login");
    } catch (err) {
      setError(toUserFacingError(err));
      setLoggingOut(false);
    }
  };

  return (
    <div className="app-shell flex h-screen">
      <aside className="flex w-52 shrink-0 flex-col border-r border-surface-border bg-surface-raised sm:w-56">
        <div className="border-b border-surface-border p-3">
          <button
            type="button"
            onClick={handleNewSession}
            disabled={loggingOut || restoringSession}
            className="w-full rounded-lg border border-surface-border px-3 py-2 text-left text-xs font-medium text-neutral-300 transition-colors hover:border-neutral-500 hover:bg-neutral-900/60 hover:text-white disabled:opacity-50"
          >
            New Session
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <p className="mb-2 px-1 text-[10px] font-medium uppercase tracking-widest text-neutral-500">
            Recent Conversations
          </p>
          {recentSessions.length === 0 ? (
            <p className="px-1 text-xs text-neutral-600">No prior chats yet</p>
          ) : (
            <ul className="space-y-0.5">
              {recentSessions.map((item) => {
                const active = item.session_id === sessionId;
                const deleting = deletingSessionId === item.session_id;
                return (
                  <li key={item.session_id} className="group flex items-center gap-0.5">
                    <button
                      type="button"
                      onClick={() => void handleSelectRecent(item.session_id)}
                      disabled={
                        loading ||
                        restoringSession ||
                        active ||
                        deletingSessionId !== null
                      }
                      title={item.title}
                      className={`min-w-0 flex-1 truncate rounded-lg px-2 py-1.5 text-left text-xs transition-colors disabled:cursor-default disabled:opacity-60 ${
                        active
                          ? "bg-neutral-800 text-white"
                          : "text-neutral-400 hover:bg-neutral-900/60 hover:text-neutral-200"
                      }`}
                    >
                      {item.title}
                    </button>
                    <button
                      type="button"
                      onClick={(e) =>
                        void handleDeleteRecentSession(item.session_id, e)
                      }
                      disabled={deleting || deletingSessionId !== null}
                      aria-label={`Delete conversation: ${item.title}`}
                      title="Delete conversation"
                      className="shrink-0 rounded-md p-1.5 text-neutral-600 opacity-0 transition-opacity hover:bg-neutral-900/80 hover:text-neutral-300 group-hover:opacity-100 disabled:opacity-40"
                    >
                      <RecycleBinIcon className="h-3.5 w-3.5" />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
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
            <MessageBubble
              key={msg.id}
              message={msg}
              onDelete={() => void handleDeleteMessage(msg)}
              disabled={loading || restoringSession}
            />
          ))}
          {(loading || restoringSession) && <LoadingBubble />}
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
                disabled={loading || restoringSession}
                className="min-w-0 flex-1 rounded-xl border border-surface-border bg-black px-4 py-3 text-[15px] leading-snug text-neutral-100 placeholder:text-neutral-600 focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={loading || restoringSession || !input.trim()}
                className="shrink-0 rounded-xl bg-white px-5 py-3 text-sm font-semibold text-black transition-colors hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Send
              </button>
            </form>
          </div>
        </div>
      </main>
      </div>
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

function RecycleBinIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M4 7h16" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
      <path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12" />
      <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

function MessageLabelBar({
  label,
  align,
  onDelete,
  disabled,
}: {
  label: string;
  align: "left" | "right";
  onDelete: () => void;
  disabled?: boolean;
}) {
  return (
    <div
      className={`flex items-center gap-2 ${align === "right" ? "justify-end pr-1" : ""}`}
    >
      <span className="text-[11px] font-medium uppercase tracking-wider text-neutral-500">
        {label}
      </span>
      <button
        type="button"
        onClick={onDelete}
        disabled={disabled}
        aria-label={`Delete ${label.toLowerCase()} message`}
        title="Delete message"
        className="rounded p-0.5 text-neutral-600 transition-colors hover:bg-neutral-800 hover:text-neutral-300 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <RecycleBinIcon className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

function MessageBubble({
  message,
  onDelete,
  disabled,
}: {
  message: ChatMessage;
  onDelete: () => void;
  disabled?: boolean;
}) {
  if (message.role === "status") {
    return (
      <p className="text-center text-xs text-neutral-600">{message.content}</p>
    );
  }

  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex flex-col items-end gap-1.5">
        <MessageLabelBar
          label="You"
          align="right"
          onDelete={onDelete}
          disabled={disabled}
        />
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
        <MessageLabelBar
          label="Assistant"
          align="left"
          onDelete={onDelete}
          disabled={disabled}
        />
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
