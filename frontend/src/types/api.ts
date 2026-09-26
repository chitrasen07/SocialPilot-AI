export type Role = "owner" | "admin" | "agent" | "viewer";

export interface User {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
  email_verified: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  role: Role;
  created_at: string;
}

export interface MeResponse {
  user: User;
  organizations: Organization[];
}

export interface SyncResponse extends MeResponse {
  is_new_user: boolean;
}

export interface InstagramAccount {
  id: string;
  instagram_account_id: string;
  username: string;
  account_type: string | null;
  connection_status: "connected" | "needs_reauth" | "disconnected";
  scopes: string[];
  token_expires_at: string | null;
  connected_at: string | null;
  last_webhook_at: string | null;
}

export interface ListResponse<T> {
  items: T[];
}

export interface PageResponse<T> extends ListResponse<T> {
  has_more: boolean;
}

export interface Customer {
  id: string;
  instagram_account_id: string;
  instagram_user_id: string;
  username: string | null;
  display_name: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CustomerListItem extends Customer {
  last_message_at: string | null;
  conversation_count: number;
}

export type ConversationStatus = "open" | "pending" | "closed";

export interface CustomerDetail extends Customer {
  conversations: { id: string; status: ConversationStatus; last_message_at: string | null; created_at: string }[];
}

export type MemoryType = "preference" | "interest" | "fact" | "interaction_summary";

export interface CustomerMemory {
  id: string;
  customer_id: string;
  memory_type: MemoryType;
  content: string;
  importance: number;
  metadata: Record<string, unknown> | null;
  has_embedding: boolean;
  created_at: string;
  updated_at: string;
}

export type SenderType = "customer" | "business" | "system";
export type MessageType = "text" | "image" | "video" | "audio" | "unknown";

export interface Conversation {
  id: string;
  instagram_account_id: string;
  status: ConversationStatus;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
  customer: Customer;
}

export interface ConversationListItem extends Conversation {
  last_message: { content: string | null; sender_type: SenderType; message_type: MessageType; sent_at: string } | null;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_type: SenderType;
  message_type: MessageType;
  content: string | null;
  metadata: { attachments?: { type: string | null; url: string | null }[]; deleted?: boolean } | null;
  sent_at: string;
}

export interface MessagePage {
  items: Message[];
  next_cursor: string | null;
}

export interface ConversationDetail extends Conversation {
  messages: MessagePage;
}

export interface AIAnalysis {
  message_id: string;
  language: string;
  intent: string;
  sentiment: string;
  emotion: string;
  purchase_intent: string;
  provider: string;
  model: string;
}

export interface AIDraft {
  id: string;
  message_id: string;
  conversation_id: string;
  reply_text: string | null;
  status: "generated" | "approved" | "rejected" | "expired";
  guardrail_status: "passed" | "blocked";
  provider: string;
  model: string;
  sent: false;
}

export interface AIMessageState {
  analysis: AIAnalysis | null;
  draft: AIDraft | null;
}

export interface AISettings {
  provider: string;
  model: string;
  enabled: boolean;
  temperature: number;
  max_output_tokens: number;
  max_context_messages: number;
  memory_top_k: number;
  auto_analysis_enabled: boolean;
  configured: boolean;
}
