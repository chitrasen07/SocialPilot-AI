import { useState } from "react";
import { Link } from "react-router";
import { useAuth } from "../auth/context";
import { Alert } from "../components/forms";
import { useApiQuery } from "../hooks/useApiQuery";
import { ApiError, api } from "../lib/api";
import { canManageInbox, formatDateTime } from "../lib/inbox";
import type { AIDraft, ReviewQueueItem } from "../types/api";

const FILTERS = [
  ["all", "All"],
  ["review_required", "Review required"],
  ["high", "High risk"],
  ["medium", "Medium risk"],
  ["low", "Low risk"],
  ["escalated", "Escalated"],
] as const;

const STATUS: Record<string, string> = {
  generated: "Draft",
  review_required: "Review required",
  approved: "Approved",
  rejected: "Rejected",
  edited: "Edited",
  expired: "Expired",
};

export default function ReviewPage() {
  const { organization } = useAuth();
  const [filter, setFilter] = useState<(typeof FILTERS)[number][0]>("review_required");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const canReview = canManageInbox(organization?.role);
  const path = organization ? `/api/ai/review-queue?filter=${filter}` : null;
  const queue = useApiQuery<{ items: ReviewQueueItem[]; has_more: boolean }>(path, organization?.id);

  async function act(id: string, action: "approve" | "reject" | "escalate" | "edit", text?: string) {
    setBusy(id + action);
    setError(null);
    try {
      const body =
        action === "edit" ? { text } : action === "reject" ? { review_note: null } : action === "escalate" ? {} : undefined;
      await api<AIDraft>(`/api/ai/drafts/${id}/${action}`, {
        method: "POST",
        organizationId: organization?.id,
        body: body ?? {},
      });
      setEditing(null);
      queue.reload();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not update the draft.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Review</h1>
        <p className="mt-1 text-sm text-slate-600">
          Human review of AI drafts. Approving a draft does not send it to Instagram.
        </p>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Review filters">
        {FILTERS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            aria-pressed={filter === id}
            onClick={() => setFilter(id)}
            className={`rounded-full px-3 py-1 text-sm ${
              filter === id ? "bg-slate-900 text-white" : "bg-white text-slate-700 ring-1 ring-slate-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      {queue.loading && !queue.data && <p className="text-sm text-slate-500">Loading drafts…</p>}
      {queue.error && <Alert tone="error">{queue.error}</Alert>}
      {queue.data && queue.data.items.length === 0 && (
        <p className="rounded-xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500">
          No drafts in this view.
        </p>
      )}
      <ul className="space-y-3">
        {queue.data?.items.map((item) => {
          const text = item.edited_text || item.reply_text || "";
          const flags = item.guardrail_results?.flags ?? [];
          return (
            <li key={item.id} className="rounded-xl border border-slate-200 bg-white px-4 py-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">{item.customer_name}</p>
                <p className="text-xs text-slate-500">{formatDateTime(item.reviewed_at)}</p>
              </div>
              <p className="mt-1 text-sm text-slate-600">{item.message_preview || "No message text."}</p>
              <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                <div>
                  <dt className="text-slate-500">Risk</dt>
                  <dd className="font-medium uppercase">{item.risk_level}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Status</dt>
                  <dd className="font-medium">{STATUS[item.status] ?? item.status}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Escalation</dt>
                  <dd className="font-medium">{item.escalation_required ? item.escalation_reason || "Yes" : "No"}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Sent</dt>
                  <dd className="font-medium">Not sent</dd>
                </div>
              </dl>
              {editing === item.id ? (
                <textarea
                  value={editText}
                  onChange={(event) => setEditText(event.target.value)}
                  rows={4}
                  aria-label="Edited draft"
                  className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              ) : (
                <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm">{text || "No draft text."}</p>
              )}
              <p className="mt-2 text-xs text-slate-600">
                <span className="font-medium text-slate-500">Sources. </span>
                {item.sources.length === 0
                  ? "No relevant business knowledge found."
                  : item.sources.map((source) => source.document_name).join(", ")}
              </p>
              <p className="mt-1 text-xs text-slate-600">
                <span className="font-medium text-slate-500">Guardrails. </span>
                {flags.length === 0 ? "No issues." : flags.map((flag) => flag.code.replaceAll("_", " ")).join(", ")}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Link to={`/inbox?c=${item.conversation_id}`} className="text-xs font-medium text-slate-700 underline">
                  Open conversation
                </Link>
                {canReview && (
                  <>
                    <Action label="Approve" disabled={busy !== null} onClick={() => void act(item.id, "approve")} />
                    {editing === item.id ? (
                      <Action
                        label="Save edit"
                        disabled={busy !== null || !editText.trim()}
                        onClick={() => void act(item.id, "edit", editText.trim())}
                      />
                    ) : (
                      <Action
                        label="Edit"
                        disabled={busy !== null}
                        onClick={() => {
                          setEditing(item.id);
                          setEditText(text);
                        }}
                      />
                    )}
                    <Action label="Reject" disabled={busy !== null} onClick={() => void act(item.id, "reject")} />
                    <Action label="Escalate" disabled={busy !== null} onClick={() => void act(item.id, "escalate")} />
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Action({ label, disabled, onClick }: { label: string; disabled: boolean; onClick: () => void }) {
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
