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
  instagram_account_id: string | null;
  instagram_user_id: string | null;
  channel_type?: string;
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
  instagram_account_id: string | null;
  channel_type: string;
  priority: string;
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

export interface KnowledgeSource {
  document_id: string;
  document_name: string;
  chunk_id: string;
  page: number | null;
  chunk_index: number;
  relevance: number;
}

export type DraftStatus =
  | "generated"
  | "review_required"
  | "approved"
  | "rejected"
  | "edited"
  | "expired";

export interface GuardrailFlag {
  code: string;
  severity: string;
}

export interface AIDraft {
  id: string;
  message_id: string;
  conversation_id: string;
  reply_text: string | null;
  status: DraftStatus;
  guardrail_status: "passed" | "blocked";
  provider: string;
  model: string;
  sent: false;
  sources: KnowledgeSource[];
  risk_level: "low" | "medium" | "high";
  escalation_required: boolean;
  escalation_reason: string | null;
  guardrail_results: { blocked: boolean; flags: GuardrailFlag[] };
  edited_text: string | null;
  review_note: string | null;
  reviewed_at: string | null;
}

export interface ReviewQueueItem extends AIDraft {
  customer_name: string;
  message_preview: string;
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
  knowledge_enabled: boolean;
  knowledge_top_k: number;
  knowledge_max_distance: number;
  personality: "professional" | "friendly" | "casual" | "premium" | "playful" | "custom";
  brand_voice: string;
  custom_instructions: string;
  preferred_terms: string[];
  forbidden_terms: string[];
  emoji_policy: "none" | "minimal" | "moderate" | "match_customer";
  response_length: "short" | "medium" | "long";
  language_mode: "auto" | "english" | "hindi" | "hinglish" | "telugu";
  require_review_for_refunds: boolean;
  require_review_for_payment_issues: boolean;
  require_review_for_high_risk: boolean;
  require_review_for_unsupported_claims: boolean;
  updated_at: string | null;
  configured: boolean;
}

export type KnowledgeDocumentStatus = "pending" | "processing" | "ready" | "failed" | "deleted";

export interface KnowledgeDocument {
  id: string;
  name: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  status: KnowledgeDocumentStatus;
  chunk_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  processed_at: string | null;
}

export interface CustomerIntelligence {
  summary: string;
  preferences: string[];
  interests: string[];
  frequent_products: string[];
  buying_intent: string;
  communication_style: string;
  language_preference: string;
  previous_issues: string[];
  sentiment_trend: string;
  segments: { segment: string; confidence: number }[];
  pending_suggestions: number;
}

export interface MemorySuggestion {
  id: string;
  customer_id: string;
  source_message_id: string | null;
  content: string;
  category: "preference" | "communication" | "shopping";
  status: "pending" | "approved" | "rejected";
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
}

export interface AnalyticsDay {
  day: string;
  total_messages: number;
  total_conversations: number;
  ai_generated: number;
  approved: number;
  edited: number;
  rejected: number;
  escalated: number;
}

export interface AnalyticsTotals {
  total_messages: number;
  total_conversations: number;
  ai_generated: number;
  approved: number;
  edited: number;
  rejected: number;
  escalated: number;
  approval_rate: number;
}

export interface AnalyticsOverview {
  days: AnalyticsDay[];
  totals: AnalyticsTotals;
  average_response_seconds: number | null;
  sentiment: { sentiment: string; count: number }[];
  top_questions: { intent: string; count: number }[];
  products: { product: string; count: number }[];
  problems: { intent: string; count: number }[];
}

export interface AnalyticsCustomers {
  segments: { segment: string; customers: number }[];
}

export type AutomationTrigger =
  | "message_received"
  | "sentiment_changed"
  | "intent_detected"
  | "customer_created"
  | "segment_changed";

export type AutomationAction = "generate_draft" | "create_task" | "notify_agent";

export interface AutomationRule {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  trigger_type: AutomationTrigger;
  conditions: Record<string, string>;
  action_type: AutomationAction;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export type TaskStatus = "open" | "in_progress" | "completed" | "cancelled";
export type TaskPriority = "low" | "medium" | "high";

export interface WorkTask {
  id: string;
  customer_id: string | null;
  conversation_id: string | null;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  assigned_to: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface AppNotification {
  id: string;
  type: string;
  title: string;
  message: string;
  read: boolean;
  created_at: string;
}

export interface CustomerInsights {
  lifecycle_stage: string;
  lead_score: number;
  score_reason: string;
  buying_probability: number;
  churn_risk: number;
  recommended_actions: string[];
  recommendations: { product_name: string; reason: string; confidence: number }[];
}

export interface EngagementDashboard {
  total_conversations: number;
  qualified_leads: number;
  funnel: { stage: string; customers: number }[];
  average_lead_score: number | null;
  top_intents: { intent: string; count: number }[];
  top_products: { product: string; count: number }[];
  churn_risk_customers: { customer_id: string; display_name: string | null; churn_probability: number }[];
  ai_improvement_score: number;
  learning: {
    accepted: number;
    edited: number;
    rejected: number;
    best_personality: string | null;
    best_response_length: string | null;
    best_language_style: string | null;
    best_emoji_usage: string | null;
  };
}

export interface KnowledgeSearchHit {
  document_id: string;
  document_name: string;
  chunk_id: string;
  page: number | null;
  chunk_index: number;
  content: string;
  relevance: number;
  distance: number;
}
