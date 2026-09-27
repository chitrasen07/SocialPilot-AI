import { type FormEvent, useState } from "react";
import { Link, useParams } from "react-router";
import { useAuth } from "../auth/context";
import { Alert } from "../components/forms";
import { useApiQuery } from "../hooks/useApiQuery";
import { ApiError, api } from "../lib/api";
import { STATUS_BADGE, canManageInbox, customerName, formatDateTime } from "../lib/inbox";
import type {
  CustomerDetail,
  CustomerInsights,
  CustomerIntelligence,
  CustomerMemory,
  ListResponse,
  MemorySuggestion,
  MemoryType,
} from "../types/api";

const MEMORY_TYPES: { value: MemoryType; label: string }[] = [
  { value: "preference", label: "Preference" },
  { value: "interest", label: "Interest" },
  { value: "fact", label: "Fact" },
  { value: "interaction_summary", label: "Interaction summary" },
];

export default function CustomerDetailPage() {
  const { customerId } = useParams();
  const { organization } = useAuth();
  const organizationId = organization?.id;
  const canManage = canManageInbox(organization?.role);
  const customer = useApiQuery<CustomerDetail>(`/api/customers/${customerId}`, organizationId);
  const memories = useApiQuery<ListResponse<CustomerMemory>>(`/api/customers/${customerId}/memories`, organizationId);
  const intelligence = useApiQuery<CustomerIntelligence>(
    customerId ? `/api/customers/${customerId}/intelligence` : null,
    organizationId,
  );
  const insights = useApiQuery<CustomerInsights>(
    customerId ? `/api/intelligence/customers/${customerId}` : null,
    organizationId,
  );
  const suggestions = useApiQuery<ListResponse<MemorySuggestion>>(
    customerId ? `/api/customers/${customerId}/memory-suggestions` : null,
    organizationId,
  );

  const [memoryType, setMemoryType] = useState<MemoryType>("preference");
  const [content, setContent] = useState("");
  const [importance, setImportance] = useState("1");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  async function addMemory(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      await api(`/api/customers/${customerId}/memories`, {
        method: "POST",
        body: { memory_type: memoryType, content, importance: Number(importance) },
        organizationId,
      });
      setContent("");
      memories.reload();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "Could not save the memory.");
    } finally {
      setBusy(false);
    }
  }

  async function reviewSuggestion(id: string, action: "approve" | "reject") {
    setBusy(true);
    setNotice(null);
    try {
      await api(`/api/memory-suggestions/${id}/${action}`, { method: "POST", organizationId });
      suggestions.reload();
      memories.reload();
      intelligence.reload();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "Could not review the suggestion.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteMemory(memory: CustomerMemory) {
    if (!window.confirm("Delete this memory?")) return;
    setBusy(true);
    setNotice(null);
    try {
      await api(`/api/customers/${customerId}/memories/${memory.id}`, { method: "DELETE", organizationId });
      memories.reload();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "Could not delete the memory.");
    } finally {
      setBusy(false);
    }
  }

  if (customer.error) {
    return (
      <div className="max-w-3xl">
        <Link to="/customers" className="text-sm text-brand-600 hover:underline">
          ← Customers
        </Link>
        <div className="mt-4">
          <Alert tone="error">{customer.error}</Alert>
        </div>
      </div>
    );
  }
  const profile = customer.data;
  if (!profile) return <p className="text-sm text-slate-500">Loading…</p>;

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <Link to="/customers" className="text-sm text-brand-600 hover:underline">
          ← Customers
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">{customerName(profile)}</h1>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
        <h2 className="font-semibold">Profile</h2>
        <dl className="mt-3 grid grid-cols-[10rem_1fr] gap-y-1.5 text-sm">
          <dt className="text-slate-500">Username</dt>
          <dd>{profile.username ? `@${profile.username}` : "—"}</dd>
          <dt className="text-slate-500">Display name</dt>
          <dd>{profile.display_name ?? "—"}</dd>
          <dt className="text-slate-500">Instagram user ID</dt>
          <dd className="font-mono text-xs leading-5">{profile.instagram_user_id}</dd>
          <dt className="text-slate-500">First seen</dt>
          <dd>{formatDateTime(profile.created_at)}</dd>
        </dl>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
        <h2 className="font-semibold">AI insights</h2>
        <p className="text-sm text-slate-600">From conversation messages and approved memories.</p>
        {insights.data && (
          <dl className="mt-3 grid grid-cols-[10rem_1fr] gap-y-1.5 text-sm">
            <dt className="text-slate-500">Lifecycle stage</dt>
            <dd className="capitalize">{insights.data.lifecycle_stage.replaceAll("_", " ")}</dd>
            <dt className="text-slate-500">Lead score</dt>
            <dd>
              {insights.data.lead_score}
              {insights.data.score_reason ? ` · ${insights.data.score_reason}` : ""}
            </dd>
            <dt className="text-slate-500">Buying probability</dt>
            <dd>{Math.round(insights.data.buying_probability * 100)}%</dd>
            <dt className="text-slate-500">Churn risk</dt>
            <dd>{Math.round(insights.data.churn_risk * 100)}%</dd>
            <dt className="text-slate-500">Recommended actions</dt>
            <dd>{insights.data.recommended_actions.join(" ") || "—"}</dd>
            <dt className="text-slate-500">Products</dt>
            <dd>
              {insights.data.recommendations.map((item) => item.product_name).join(", ") || "—"}
            </dd>
          </dl>
        )}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
        <h2 className="font-semibold">What we know</h2>
        <p className="text-sm text-slate-600">Built from messages, approved memories, and message analysis.</p>
        {intelligence.data && (
          <dl className="mt-3 grid grid-cols-[10rem_1fr] gap-y-1.5 text-sm">
            <dt className="text-slate-500">Language</dt>
            <dd className="capitalize">{intelligence.data.language_preference}</dd>
            <dt className="text-slate-500">Style</dt>
            <dd className="capitalize">{intelligence.data.communication_style}</dd>
            <dt className="text-slate-500">Buying intent</dt>
            <dd className="capitalize">{intelligence.data.buying_intent}</dd>
            <dt className="text-slate-500">Sentiment</dt>
            <dd className="capitalize">{intelligence.data.sentiment_trend}</dd>
            <dt className="text-slate-500">Products</dt>
            <dd>{intelligence.data.frequent_products.join(", ") || "—"}</dd>
            <dt className="text-slate-500">Preferences</dt>
            <dd>{intelligence.data.preferences.join("; ") || "—"}</dd>
            <dt className="text-slate-500">Segments</dt>
            <dd>{intelligence.data.segments.map((item) => item.segment.replaceAll("_", " ")).join(", ") || "—"}</dd>
          </dl>
        )}
        {suggestions.data && suggestions.data.items.filter((item) => item.status === "pending").length > 0 && (
          <ul className="mt-4 space-y-2">
            {suggestions.data.items
              .filter((item) => item.status === "pending")
              .map((item) => (
                <li key={item.id} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500">{item.category}</p>
                  <p>{item.content}</p>
                  {canManage && (
                    <div className="mt-2 flex gap-3">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void reviewSuggestion(item.id, "approve")}
                        className="text-brand-600 hover:underline disabled:opacity-60"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void reviewSuggestion(item.id, "reject")}
                        className="text-red-600 hover:underline disabled:opacity-60"
                      >
                        Reject
                      </button>
                    </div>
                  )}
                </li>
              ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
        <h2 className="font-semibold">Conversations</h2>
        {profile.conversations.length === 0 && <p className="mt-2 text-sm text-slate-500">No conversations.</p>}
        <ul className="mt-2 divide-y divide-slate-100 text-sm">
          {profile.conversations.map((conversation) => (
            <li key={conversation.id} className="flex items-center justify-between py-2">
              <Link to={`/inbox?c=${conversation.id}`} className="text-brand-600 hover:underline">
                Last message {formatDateTime(conversation.last_message_at)}
              </Link>
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[conversation.status]}`}>
                {conversation.status}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
        <h2 className="font-semibold">Memory</h2>
        <p className="text-sm text-slate-600">Notes about this customer that your team wants to remember.</p>
        {notice && (
          <div className="mt-3">
            <Alert tone="error">{notice}</Alert>
          </div>
        )}
        {memories.error && (
          <div className="mt-3">
            <Alert tone="error">{memories.error}</Alert>
          </div>
        )}
        {memories.data?.items.length === 0 && <p className="mt-3 text-sm text-slate-500">Nothing saved yet.</p>}
        <ul className="mt-3 space-y-2">
          {memories.data?.items.map((memory) => (
            <li key={memory.id} className="flex items-start justify-between gap-4 rounded-lg bg-slate-50 px-3 py-2 text-sm">
              <div>
                <p className="text-[11px] uppercase tracking-wide text-slate-500">
                  {memory.memory_type.replace("_", " ")} · importance {memory.importance}
                </p>
                <p>{memory.content}</p>
              </div>
              {canManage && (
                <button
                  onClick={() => void deleteMemory(memory)}
                  disabled={busy}
                  className="shrink-0 text-red-600 hover:underline disabled:opacity-60"
                >
                  Delete
                </button>
              )}
            </li>
          ))}
        </ul>

        {canManage && (
          <form onSubmit={(event) => void addMemory(event)} className="mt-4 space-y-3 border-t border-slate-100 pt-4">
            <div className="flex gap-3">
              <select
                value={memoryType}
                onChange={(event) => setMemoryType(event.target.value as MemoryType)}
                className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
              >
                {MEMORY_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                Importance
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.1}
                  value={importance}
                  onChange={(event) => setImportance(event.target.value)}
                  className="w-20 rounded-lg border border-slate-300 px-2 py-1.5"
                />
              </label>
            </div>
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              placeholder="e.g. Prefers blue shoes"
              maxLength={2000}
              rows={2}
              required
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={busy || !content.trim()}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500 disabled:opacity-60"
            >
              Add memory
            </button>
          </form>
        )}
      </section>
    </div>
  );
}
