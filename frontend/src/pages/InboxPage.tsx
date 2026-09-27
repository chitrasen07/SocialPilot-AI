import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useAuth } from "../auth/context";
import { Alert } from "../components/forms";
import { useApiQuery } from "../hooks/useApiQuery";
import { ApiError, api } from "../lib/api";
import { STATUS_BADGE, canManageInbox, customerName, formatDateTime, messageText } from "../lib/inbox";
import type {
  AIAnalysis,
  AIDraft,
  AIMessageState,
  Conversation,
  ConversationDetail,
  ConversationListItem,
  ConversationStatus,
  CustomerMemory,
  ListResponse,
  Message,
  MessagePage,
  PageResponse,
} from "../types/api";

const PAGE_SIZE = 50;
const FILTERS: { value: ConversationStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "open", label: "Open" },
  { value: "pending", label: "Pending" },
  { value: "closed", label: "Closed" },
];

const CHANNELS = ["all", "instagram", "whatsapp", "messenger", "email", "webchat"] as const;
const PRIORITIES = ["all", "low", "medium", "high"] as const;

export default function InboxPage() {
  const { organization } = useAuth();
  const organizationId = organization?.id;
  const [params, setParams] = useSearchParams();
  const selectedId = params.get("c");
  const [filter, setFilter] = useState<ConversationStatus | "all">("all");
  const [channel, setChannel] = useState<(typeof CHANNELS)[number]>("all");
  const [priority, setPriority] = useState<(typeof PRIORITIES)[number]>("all");
  const [offset, setOffset] = useState(0);

  const listPath = `/api/conversations?limit=${PAGE_SIZE}&offset=${offset}${filter === "all" ? "" : `&status=${filter}`}${channel === "all" ? "" : `&channel=${channel}`}${priority === "all" ? "" : `&priority=${priority}`}`;
  const list = useApiQuery<PageResponse<ConversationListItem>>(listPath, organizationId);
  const detail = useApiQuery<ConversationDetail>(
    selectedId ? `/api/conversations/${selectedId}` : null,
    organizationId,
  );
  const conversation = detail.data?.id === selectedId ? detail.data : null;

  function select(id: string) {
    setParams({ c: id });
  }

  function onStatusChanged(updated: Conversation) {
    detail.setData((current) => (current ? { ...current, ...updated } : current));
    list.reload();
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      <div className="mb-4">
        <h1 className="text-2xl font-semibold">Inbox</h1>
        <p className="mt-1 text-sm text-slate-600">
          Conversations from Instagram, WhatsApp, Messenger, email, and the website widget.
        </p>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-[20rem_1fr_18rem] overflow-hidden rounded-xl border border-slate-200 bg-white">
        <section className="flex min-h-0 flex-col border-r border-slate-200">
          <div className="flex flex-wrap gap-1 border-b border-slate-200 p-2">
            {CHANNELS.map((value) => (
              <button
                key={value}
                onClick={() => {
                  setChannel(value);
                  setOffset(0);
                }}
                className={`rounded-md px-2 py-1 text-xs capitalize ${channel === value ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"}`}
              >
                {value === "webchat" ? "Website" : value}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1 border-b border-slate-200 p-2">
            {PRIORITIES.map((value) => (
              <button
                key={value}
                onClick={() => {
                  setPriority(value);
                  setOffset(0);
                }}
                className={`rounded-md px-2 py-1 text-xs capitalize ${priority === value ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}
              >
                {value === "all" ? "Any priority" : value}
              </button>
            ))}
          </div>
          <div className="flex gap-1 border-b border-slate-200 p-2">
            {FILTERS.map((option) => (
              <button
                key={option.value}
                onClick={() => {
                  setFilter(option.value);
                  setOffset(0);
                }}
                className={`rounded-md px-2.5 py-1 text-xs font-medium ${filter === option.value ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {list.error && (
              <div className="p-3">
                <Alert tone="error">{list.error}</Alert>
              </div>
            )}
            {list.data?.items.length === 0 && (
              <p className="p-4 text-sm text-slate-500">
                No conversations yet. They appear here when a customer messages a connected channel.
              </p>
            )}
            <ul>
              {list.data?.items.map((item) => (
                <li key={item.id}>
                  <button
                    onClick={() => select(item.id)}
                    className={`block w-full border-b border-slate-100 px-4 py-3 text-left hover:bg-slate-50 ${item.id === selectedId ? "bg-slate-100" : ""}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{customerName(item.customer)}</span>
                      <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_BADGE[item.status]}`}>
                        {item.status}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-sm text-slate-600">
                      {item.last_message
                        ? `${item.last_message.sender_type === "business" ? "You: " : ""}${messageText(item.last_message)}`
                        : "No messages"}
                    </p>
                    <p className="mt-0.5 text-xs capitalize text-slate-400">
                      {item.channel_type === "webchat" ? "Website" : item.channel_type} · {item.priority} ·{" "}
                      {formatDateTime(item.last_message_at)}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          </div>
          {(offset > 0 || list.data?.has_more) && (
            <div className="flex justify-between border-t border-slate-200 px-3 py-2 text-sm">
              <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} className="text-brand-600 disabled:text-slate-300">
                Newer
              </button>
              <button disabled={!list.data?.has_more} onClick={() => setOffset(offset + PAGE_SIZE)} className="text-brand-600 disabled:text-slate-300">
                Older
              </button>
            </div>
          )}
        </section>

        <section className="flex min-h-0 flex-col">
          {!selectedId && <p className="m-auto text-sm text-slate-500">Select a conversation to read it.</p>}
          {selectedId && detail.error && (
            <div className="p-4">
              <Alert tone="error">{detail.error}</Alert>
            </div>
          )}
          {selectedId && !conversation && !detail.error && <p className="m-auto text-sm text-slate-500">Loading…</p>}
          {conversation && organizationId && (
            <MessageThread key={conversation.id} conversation={conversation} organizationId={organizationId} />
          )}
          {conversation && organizationId && (
            <AiPanel
              key={`${conversation.id}-ai`}
              messages={conversation.messages.items}
              organizationId={organizationId}
              canGenerate={canManageInbox(organization?.role)}
            />
          )}
        </section>

        <aside className="min-h-0 overflow-y-auto border-l border-slate-200">
          {conversation && organizationId && (
            <CustomerPanel
              key={conversation.id}
              conversation={conversation}
              organizationId={organizationId}
              canManage={canManageInbox(organization?.role)}
              onStatusChanged={onStatusChanged}
            />
          )}
        </aside>
      </div>
    </div>
  );
}

const LABELS: Record<string, string> = {
  english: "English",
  hindi: "Hindi",
  hinglish: "Hinglish",
  telugu: "Telugu",
  mixed: "Mixed",
  unknown: "Unknown",
  product_question: "Product question",
  pricing_question: "Pricing question",
  availability_question: "Availability question",
  purchase_question: "Purchase question",
  order_status: "Order status",
  shipping_question: "Shipping question",
  refund_request: "Refund request",
  complaint: "Complaint",
  support_request: "Support request",
  greeting: "Greeting",
  general_question: "General question",
  feedback: "Feedback",
  spam: "Spam",
  positive: "Positive",
  neutral: "Neutral",
  negative: "Negative",
  joy: "Joy",
  interest: "Interest",
  frustration: "Frustration",
  anger: "Anger",
  confusion: "Confusion",
  urgency: "Urgency",
  disappointment: "Disappointment",
  high: "High",
  medium: "Medium",
  low: "Low",
  none: "None",
};

function label(value: string): string {
  return LABELS[value] ?? value;
}

function AiPanel({
  messages,
  organizationId,
  canGenerate,
}: {
  messages: Message[];
  organizationId: string;
  canGenerate: boolean;
}) {
  const latest = [...messages].reverse().find((message) => message.sender_type === "customer");
  const latestId = latest?.id;
  const [state, setState] = useState<AIMessageState | null>(null);
  const [draftText, setDraftText] = useState("");
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!latestId) return;
    let active = true;
    api<AIMessageState>(`/api/ai/messages/${latestId}`, { organizationId })
      .then((loaded) => {
        if (!active) return;
        setState(loaded);
        setDraftText(loaded.draft?.edited_text || loaded.draft?.reply_text || "");
      })
      .catch(() => {
        if (active) setState(null);
      });
    return () => {
      active = false;
    };
  }, [latestId, organizationId]);

  if (!latest) return null;

  async function reloadDraft() {
    const loaded = await api<AIMessageState>(`/api/ai/messages/${latestId}`, { organizationId });
    setState(loaded);
    setDraftText(loaded.draft?.edited_text || loaded.draft?.reply_text || "");
    setEditing(false);
  }

  async function run(path: string, kind: "analyze" | "reply") {
    setBusy(kind);
    setError(null);
    try {
      if (kind === "analyze") {
        const analysis = await api<AIAnalysis>(path, {
          method: "POST",
          body: { message_id: latestId },
          organizationId,
        });
        setState((current) => ({ analysis, draft: current?.draft ?? null }));
      } else {
        await api<AIDraft>(path, {
          method: "POST",
          body: { message_id: latestId },
          organizationId,
        });
        await reloadDraft();
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(null);
    }
  }

  async function review(action: "approve" | "reject" | "escalate" | "edit") {
    if (!state?.draft) return;
    setBusy(action);
    setError(null);
    try {
      const body = action === "edit" ? { text: draftText.trim() } : {};
      await api<AIDraft>(`/api/ai/drafts/${state.draft.id}/${action}`, {
        method: "POST",
        organizationId,
        body,
      });
      await reloadDraft();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not update the draft.");
    } finally {
      setBusy(null);
    }
  }

  const analysis = state?.analysis;

  return (
    <div className="border-t border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">AI draft</h3>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => void run("/api/ai/analyze-message", "analyze")}
            className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium hover:bg-slate-50 disabled:opacity-60"
          >
            {busy === "analyze" ? "Analyzing…" : analysis ? "Re-analyze" : "Analyze"}
          </button>
          {canGenerate && (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => void run("/api/ai/generate-reply", "reply")}
              className="rounded-md bg-slate-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {busy === "reply" ? "Generating…" : state?.draft ? "Regenerate" : "Generate AI reply"}
            </button>
          )}
        </div>
      </div>
      {error && (
        <div className="mt-3">
          <Alert tone="error">{error}</Alert>
        </div>
      )}
      {analysis ? (
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-5">
          <Signal label="Language" value={label(analysis.language)} />
          <Signal label="Intent" value={label(analysis.intent)} />
          <Signal label="Sentiment" value={label(analysis.sentiment)} />
          <Signal label="Emotion" value={label(analysis.emotion)} />
          <Signal label="Purchase intent" value={label(analysis.purchase_intent)} />
        </dl>
      ) : (
        <p className="mt-3 text-xs text-slate-500">No analysis yet for the latest customer message.</p>
      )}
      {state?.draft && (
        <DraftDetails
          draft={state.draft}
          draftText={draftText}
          editing={editing}
          busy={busy}
          canReview={canGenerate}
          onChange={setDraftText}
          onEdit={() => {
            setDraftText(state.draft?.edited_text || state.draft?.reply_text || "");
            setEditing(true);
          }}
          onSave={() => void review("edit")}
          onApprove={() => void review("approve")}
          onReject={() => void review("reject")}
          onEscalate={() => void review("escalate")}
        />
      )}
    </div>
  );
}

const DRAFT_STATUS: Record<string, string> = {
  generated: "Draft",
  review_required: "Review required",
  approved: "Approved",
  rejected: "Rejected",
  edited: "Edited",
  expired: "Expired",
};

function DraftDetails({
  draft,
  draftText,
  editing,
  busy,
  canReview,
  onChange,
  onEdit,
  onSave,
  onApprove,
  onReject,
  onEscalate,
}: {
  draft: AIDraft;
  draftText: string;
  editing: boolean;
  busy: string | null;
  canReview: boolean;
  onChange: (value: string) => void;
  onEdit: () => void;
  onSave: () => void;
  onApprove: () => void;
  onReject: () => void;
  onEscalate: () => void;
}) {
  const flags = draft.guardrail_results?.flags ?? [];
  return (
    <div className="mt-3">
      <p className="text-xs font-medium text-slate-500">Draft only — nothing is sent to Instagram</p>
      <dl className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
        <div>
          <dt className="text-slate-500">Risk</dt>
          <dd className="font-medium uppercase">{draft.risk_level}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Status</dt>
          <dd className="font-medium">{DRAFT_STATUS[draft.status] ?? draft.status}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Sent</dt>
          <dd className="font-medium">Not sent</dd>
        </div>
      </dl>
      {editing ? (
        <textarea
          value={draftText}
          onChange={(event) => onChange(event.target.value)}
          rows={3}
          aria-label="Edit AI draft"
          className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
      ) : (
        <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-800">
          {draftText || "No safe draft text."}
        </p>
      )}
      <div className="mt-2 text-xs text-slate-600">
        <p className="font-medium text-slate-500">Sources used</p>
        {draft.sources.length === 0 ? (
          <p className="mt-1">No relevant business knowledge found.</p>
        ) : (
          <ul className="mt-1 space-y-1">
            {draft.sources.map((source) => (
              <li key={source.chunk_id}>
                {source.document_name}
                {source.page ? ` — page ${source.page}` : ""}
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="mt-2 text-xs text-slate-600">
        <span className="font-medium text-slate-500">Guardrails. </span>
        {flags.length === 0 ? "No issues." : `Requires review: ${flags.map((flag) => flag.code.replaceAll("_", " ")).join(", ")}`}
      </p>
      {draft.escalation_required && (
        <p className="mt-1 text-xs text-amber-800">Escalated: {draft.escalation_reason || "Needs a person."}</p>
      )}
      {canReview && (
        <div className="mt-3 flex flex-wrap gap-2">
          {editing ? (
            <ReviewButton label="Save edit" disabled={busy !== null || !draftText.trim()} onClick={onSave} />
          ) : (
            <ReviewButton label="Edit" disabled={busy !== null} onClick={onEdit} />
          )}
          <ReviewButton label="Approve" disabled={busy !== null} onClick={onApprove} />
          <ReviewButton label="Reject" disabled={busy !== null} onClick={onReject} />
          <ReviewButton label="Escalate" disabled={busy !== null} onClick={onEscalate} />
        </div>
      )}
    </div>
  );
}

function ReviewButton({ label, disabled, onClick }: { label: string; disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium hover:bg-slate-50 disabled:opacity-60"
    >
      {label}
    </button>
  );
}

function Signal({ label: name, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-slate-500">{name}</dt>
      <dd className="font-medium text-slate-800">{value}</dd>
    </div>
  );
}

function MessageThread({ conversation, organizationId }: { conversation: ConversationDetail; organizationId: string }) {
  const [messages, setMessages] = useState<Message[]>(conversation.messages.items);
  const [cursor, setCursor] = useState(conversation.messages.next_cursor);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadOlder() {
    if (!cursor) return;
    setLoading(true);
    setError(null);
    try {
      const page = await api<MessagePage>(
        `/api/conversations/${conversation.id}/messages?before=${encodeURIComponent(cursor)}`,
        { organizationId },
      );
      setMessages((current) => [...page.items, ...current]);
      setCursor(page.next_cursor);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load older messages.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <header className="border-b border-slate-200 px-5 py-3">
        <p className="font-medium">{customerName(conversation.customer)}</p>
        <p className="text-xs text-slate-500">Read-only history. Replies are sent from Instagram for now.</p>
      </header>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-5 py-4">
        {cursor && (
          <div className="text-center">
            <button onClick={() => void loadOlder()} disabled={loading} className="text-sm text-brand-600 hover:underline disabled:opacity-60">
              {loading ? "Loading…" : "Load older messages"}
            </button>
          </div>
        )}
        {error && <Alert tone="error">{error}</Alert>}
        {messages.length === 0 && <p className="text-sm text-slate-500">No messages in this conversation.</p>}
        {messages.map((message) => {
          const outgoing = message.sender_type !== "customer";
          const image = message.message_type === "image" ? message.metadata?.attachments?.[0]?.url : null;
          return (
            <div key={message.id} className={`flex ${outgoing ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[75%] rounded-2xl px-3.5 py-2 text-sm ${outgoing ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-900"}`}
              >
                {image ? (
                  <a href={image} target="_blank" rel="noreferrer noopener" className="underline">
                    View photo
                  </a>
                ) : (
                  <p className={`whitespace-pre-wrap break-words ${message.metadata?.deleted ? "italic opacity-70" : ""}`}>
                    {messageText(message)}
                  </p>
                )}
                <p className={`mt-1 text-[11px] ${outgoing ? "text-white/70" : "text-slate-500"}`}>
                  {new Date(message.sent_at).toLocaleString()}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

function CustomerPanel({
  conversation,
  organizationId,
  canManage,
  onStatusChanged,
}: {
  conversation: ConversationDetail;
  organizationId: string;
  canManage: boolean;
  onStatusChanged: (updated: Conversation) => void;
}) {
  const customer = conversation.customer;
  const memories = useApiQuery<ListResponse<CustomerMemory>>(`/api/customers/${customer.id}/memories`, organizationId);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function changeStatus(status: ConversationStatus) {
    setSaving(true);
    setError(null);
    try {
      const updated = await api<Conversation>(`/api/conversations/${conversation.id}`, {
        method: "PATCH",
        body: { status },
        organizationId,
      });
      onStatusChanged(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update the conversation.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6 p-4 text-sm">
      <section>
        <h2 className="text-xs font-medium uppercase tracking-wider text-slate-500">Customer</h2>
        <p className="mt-2 font-medium">{customerName(customer)}</p>
        <p className="font-mono text-xs text-slate-500">{customer.instagram_user_id}</p>
        <Link to={`/customers/${customer.id}`} className="mt-2 inline-block text-brand-600 hover:underline">
          View profile
        </Link>
      </section>

      <section>
        <h2 className="text-xs font-medium uppercase tracking-wider text-slate-500">Status</h2>
        {canManage ? (
          <select
            value={conversation.status}
            disabled={saving}
            onChange={(event) => void changeStatus(event.target.value as ConversationStatus)}
            className="mt-2 w-full rounded-lg border border-slate-300 px-2 py-1.5"
          >
            <option value="open">Open</option>
            <option value="pending">Pending</option>
            <option value="closed">Closed</option>
          </select>
        ) : (
          <p className="mt-2 capitalize">{conversation.status}</p>
        )}
        {error && (
          <div className="mt-2">
            <Alert tone="error">{error}</Alert>
          </div>
        )}
      </section>

      <section>
        <h2 className="text-xs font-medium uppercase tracking-wider text-slate-500">Memory</h2>
        {memories.error && <p className="mt-2 text-red-600">{memories.error}</p>}
        {memories.data?.items.length === 0 && <p className="mt-2 text-slate-500">Nothing saved yet.</p>}
        <ul className="mt-2 space-y-2">
          {memories.data?.items.map((memory) => (
            <li key={memory.id} className="rounded-lg bg-slate-50 px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">{memory.memory_type.replace("_", " ")}</p>
              <p>{memory.content}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
