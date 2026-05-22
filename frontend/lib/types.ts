export type ResponseStatus = "ok" | "confirmation_required" | "error";

export interface ProjectContext {
  project_id: string;
  project_name: string;
}

export interface PendingAction {
  action_id: string;
  tool: "create_task" | "update_task" | "delete_task";
  summary: string;
  payload: Record<string, unknown>;
}

export interface ChatRequest {
  message: string;
  session_id: string;
  user_id?: string | null;
  confirm?: boolean;
  cancel?: boolean;
  action_id?: string | null;
}

export interface MemoryContextResponse {
  user_id: string;
  welcome_message?: string | null;
  project_context?: ProjectContext | null;
  last_active_project?: ProjectContext | null;
  frequent_project?: ProjectContext | null;
  recent_queries?: string[];
}

export interface RecentSessionItem {
  session_id: string;
  title: string;
  updated_at: string;
}

export interface SessionRestoreResponse {
  user_id: string;
  restored: boolean;
  session_id?: string | null;
  restore_message?: string | null;
  welcome_message?: string | null;
  messages: Array<{ id?: number | null; role: string; content: string }>;
  project_context?: ProjectContext | null;
  recent_projects?: Array<{ project_id: string; name: string }>;
  last_active_project?: ProjectContext | null;
  frequent_project?: ProjectContext | null;
  recent_queries?: string[];
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  agent: string;
  routed_to?: string | null;
  status: ResponseStatus;
  requires_confirmation: boolean;
  pending_action?: PendingAction | null;
  project_context?: ProjectContext | null;
  data?: Record<string, unknown> | null;
}

export type MessageRole = "user" | "assistant" | "status";

export interface ChatMessage {
  id: string;
  dbId?: number | null;
  role: MessageRole;
  content: string;
  status?: ResponseStatus;
}
