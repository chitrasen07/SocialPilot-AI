import type { ConversationStatus, Customer, Message, MessageType, Role } from "../types/api";

export function customerName(customer: Customer) {
  if (customer.username) return `@${customer.username}`;
  return customer.display_name ?? `Instagram user ${customer.instagram_user_id}`;
}

export function formatDateTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

const MEDIA_LABELS: Record<MessageType, string> = {
  text: "",
  image: "Photo",
  video: "Video",
  audio: "Voice message",
  unknown: "Attachment",
};

export function messageText(message: Pick<Message, "content" | "message_type"> & { metadata?: Message["metadata"] }) {
  if (message.metadata?.deleted) return "Message unsent";
  return message.content ?? `[${MEDIA_LABELS[message.message_type] || "Message"}]`;
}

export const STATUS_BADGE: Record<ConversationStatus, string> = {
  open: "bg-emerald-50 text-emerald-700",
  pending: "bg-amber-50 text-amber-700",
  closed: "bg-slate-100 text-slate-600",
};

/** Agents and above can change conversation status and manage memories (mirrors the API). */
export function canManageInbox(role: Role | undefined) {
  return role === "owner" || role === "admin" || role === "agent";
}

export function canManageAutomation(role: Role | undefined) {
  return role === "owner" || role === "admin";
}
