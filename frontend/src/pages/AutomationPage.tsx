import { type FormEvent, useState } from "react";
import { useAuth } from "../auth/context";
import { Alert } from "../components/forms";
import { useApiQuery } from "../hooks/useApiQuery";
import { ApiError, api } from "../lib/api";
import { canManageAutomation } from "../lib/inbox";
import type { AutomationAction, AutomationRule, AutomationTrigger, ListResponse } from "../types/api";

const TRIGGERS: { value: AutomationTrigger; label: string }[] = [
  { value: "message_received", label: "Message received" },
  { value: "sentiment_changed", label: "Sentiment" },
  { value: "intent_detected", label: "Intent detected" },
  { value: "customer_created", label: "Customer created" },
  { value: "segment_changed", label: "Segment changed" },
];

const ACTIONS: { value: AutomationAction; label: string }[] = [
  { value: "generate_draft", label: "Generate AI draft" },
  { value: "create_task", label: "Create task" },
  { value: "notify_agent", label: "Notify agent" },
];

const EMPTY = {
  name: "",
  description: "",
  trigger_type: "intent_detected" as AutomationTrigger,
  action_type: "generate_draft" as AutomationAction,
  intent: "",
  sentiment: "",
  segment: "",
  enabled: true,
};

export default function AutomationPage() {
  const { organization } = useAuth();
  const canEdit = canManageAutomation(organization?.role);
  const rules = useApiQuery<ListResponse<AutomationRule>>(
    organization ? "/api/automation/rules" : null,
    organization?.id,
  );
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function conditions() {
    const value: Record<string, string> = {};
    if (form.intent.trim()) value.intent = form.intent.trim();
    if (form.sentiment.trim()) value.sentiment = form.sentiment.trim();
    if (form.segment.trim()) value.segment = form.segment.trim();
    return value;
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!organization) return;
    setBusy(true);
    setError(null);
    const body = {
      name: form.name,
      description: form.description,
      enabled: form.enabled,
      trigger_type: form.trigger_type,
      action_type: form.action_type,
      conditions: conditions(),
    };
    try {
      if (editing) {
        await api(`/api/automation/rules/${editing}`, { method: "PATCH", organizationId: organization.id, body });
      } else {
        await api("/api/automation/rules", { method: "POST", organizationId: organization.id, body });
      }
      setForm(EMPTY);
      setEditing(null);
      rules.reload();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not save the rule.");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(rule: AutomationRule) {
    if (!organization) return;
    await api(`/api/automation/rules/${rule.id}`, {
      method: "PATCH",
      organizationId: organization.id,
      body: { enabled: !rule.enabled },
    });
    rules.reload();
  }

  async function remove(rule: AutomationRule) {
    if (!organization || !window.confirm(`Delete “${rule.name}”?`)) return;
    await api(`/api/automation/rules/${rule.id}`, { method: "DELETE", organizationId: organization.id });
    rules.reload();
  }

  function edit(rule: AutomationRule) {
    setEditing(rule.id);
    setForm({
      name: rule.name,
      description: rule.description,
      trigger_type: rule.trigger_type,
      action_type: rule.action_type,
      intent: rule.conditions.intent ?? "",
      sentiment: rule.conditions.sentiment ?? "",
      segment: rule.conditions.segment ?? "",
      enabled: rule.enabled,
    });
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Automation</h1>
        <p className="mt-1 text-sm text-slate-600">
          Rules decide when to prepare a draft, open a task, or notify a teammate. Nothing is sent to Instagram.
        </p>
      </div>
      {rules.error && <Alert tone="error">{rules.error}</Alert>}
      {error && <Alert tone="error">{error}</Alert>}
      <ul className="space-y-3">
        {rules.data?.items.map((rule) => (
          <li key={rule.id} className="rounded-xl border border-slate-200 bg-white px-5 py-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-medium">{rule.name}</p>
                <p className="text-sm text-slate-600">{rule.description}</p>
                <p className="mt-1 text-xs uppercase tracking-wide text-slate-500">
                  {rule.trigger_type.replaceAll("_", " ")} → {rule.action_type.replaceAll("_", " ")}
                  {rule.enabled ? "" : " · disabled"}
                </p>
              </div>
              {canEdit && (
                <div className="flex shrink-0 gap-3 text-sm">
                  <button type="button" onClick={() => void toggle(rule)} className="text-brand-600 hover:underline">
                    {rule.enabled ? "Disable" : "Enable"}
                  </button>
                  <button type="button" onClick={() => edit(rule)} className="text-slate-600 hover:underline">
                    Edit
                  </button>
                  <button type="button" onClick={() => void remove(rule)} className="text-red-600 hover:underline">
                    Delete
                  </button>
                </div>
              )}
            </div>
          </li>
        ))}
        {rules.data?.items.length === 0 && <p className="text-sm text-slate-500">No rules yet.</p>}
      </ul>
      {canEdit && (
        <form onSubmit={(event) => void save(event)} className="space-y-3 rounded-xl border border-slate-200 bg-white px-5 py-4">
          <h2 className="font-semibold">{editing ? "Edit rule" : "New rule"}</h2>
          <input
            required
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            placeholder="When customer asks product price"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <textarea
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
            placeholder="What should happen"
            rows={2}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <select
              value={form.trigger_type}
              onChange={(event) => setForm({ ...form, trigger_type: event.target.value as AutomationTrigger })}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              {TRIGGERS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
            <select
              value={form.action_type}
              onChange={(event) => setForm({ ...form, action_type: event.target.value as AutomationAction })}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              {ACTIONS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <input
              value={form.intent}
              onChange={(event) => setForm({ ...form, intent: event.target.value })}
              placeholder="intent, e.g. pricing_question"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <input
              value={form.sentiment}
              onChange={(event) => setForm({ ...form, sentiment: event.target.value })}
              placeholder="sentiment, e.g. negative"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <input
              value={form.segment}
              onChange={(event) => setForm({ ...form, segment: event.target.value })}
              placeholder="segment, e.g. high_intent_buyer"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
            />
            Enabled
          </label>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500 disabled:opacity-60"
          >
            {editing ? "Save changes" : "Create rule"}
          </button>
        </form>
      )}
    </div>
  );
}
