import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth/context";
import { BrandSettings } from "../components/BrandSettings";
import { Alert, SubmitButton, TextField } from "../components/forms";
import { useApiQuery } from "../hooks/useApiQuery";
import { ApiError, api } from "../lib/api";
import type { AISettings, Organization } from "../types/api";

export default function SettingsPage() {
  const { account, organization, refreshAccount } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const canRename = organization?.role === "owner" || organization?.role === "admin";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!organization) return;
    const name = String(new FormData(event.currentTarget).get("name")).trim();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await api<Organization>(`/api/organizations/${organization.id}`, { method: "PATCH", body: { name } });
      await refreshAccount();
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save workspace settings.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-slate-600">Workspace and account details for this organization.</p>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
        <h2 className="font-semibold">Workspace</h2>
        {organization ? (
          <form onSubmit={(event) => void handleSubmit(event)} className="mt-4 space-y-4">
            {error && <Alert tone="error">{error}</Alert>}
            {saved && <Alert tone="success">Workspace name saved.</Alert>}
            <TextField
              label="Workspace name"
              name="name"
              defaultValue={organization.name}
              required
              maxLength={100}
              disabled={!canRename}
            />
            <p className="text-sm capitalize text-slate-600">Your role: {organization.role}</p>
            {canRename ? (
              <SubmitButton busy={busy}>Save</SubmitButton>
            ) : (
              <p className="text-sm text-slate-500">Ask an owner or admin to rename this workspace.</p>
            )}
          </form>
        ) : (
          <p className="mt-2 text-sm text-slate-600">You're not a member of any organization.</p>
        )}
      </section>

      {organization && canRename && <AiSettingsPanel organizationId={organization.id} />}
      {organization && canRename && <BrandSettings organizationId={organization.id} />}

      <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
        <h2 className="font-semibold">Your account</h2>
        <dl className="mt-3 grid grid-cols-[8rem_1fr] gap-y-1.5 text-sm">
          <dt className="text-slate-500">Name</dt>
          <dd>{account?.user.name ?? "—"}</dd>
          <dt className="text-slate-500">Email</dt>
          <dd>{account?.user.email}</dd>
        </dl>
      </section>
    </div>
  );
}

function AiSettingsPanel({ organizationId }: { organizationId: string }) {
  const settings = useApiQuery<AISettings>("/api/ai/settings", organizationId);
  const [temperature, setTemperature] = useState("0.4");
  const [maxTokens, setMaxTokens] = useState("256");
  const [enabled, setEnabled] = useState(true);
  const [autoAnalysis, setAutoAnalysis] = useState(false);
  const [knowledgeEnabled, setKnowledgeEnabled] = useState(true);
  const [knowledgeTopK, setKnowledgeTopK] = useState("5");
  const [knowledgeDistance, setKnowledgeDistance] = useState("0.5");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!settings.data) return;
    setTemperature(String(settings.data.temperature));
    setMaxTokens(String(settings.data.max_output_tokens));
    setEnabled(settings.data.enabled);
    setAutoAnalysis(settings.data.auto_analysis_enabled);
    setKnowledgeEnabled(settings.data.knowledge_enabled);
    setKnowledgeTopK(String(settings.data.knowledge_top_k));
    setKnowledgeDistance(String(settings.data.knowledge_max_distance));
  }, [settings.data]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await api<AISettings>("/api/ai/settings", {
        method: "PATCH",
        organizationId,
        body: {
          enabled,
          temperature: Number(temperature),
          max_output_tokens: Number(maxTokens),
          auto_analysis_enabled: autoAnalysis,
          knowledge_enabled: knowledgeEnabled,
          knowledge_top_k: Number(knowledgeTopK),
          knowledge_max_distance: Number(knowledgeDistance),
        },
      });
      setSaved(true);
      settings.reload();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not save AI settings.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
      <h2 className="font-semibold">AI</h2>
      <p className="mt-1 text-sm text-slate-500">
        Drafts stay in the inbox. SocialPilot does not send them to Instagram.
      </p>
      {settings.loading && !settings.data && <p className="mt-3 text-sm text-slate-500">Loading…</p>}
      {settings.error && (
        <div className="mt-3">
          <Alert tone="error">{settings.error}</Alert>
        </div>
      )}
      {settings.data && !settings.data.configured && (
        <p className="mt-3 text-sm text-amber-800">AI is not configured yet.</p>
      )}
      {settings.data && (
        <form onSubmit={(event) => void onSubmit(event)} className="mt-4 space-y-4">
          <p className="text-sm text-slate-600">
            Provider <span className="font-medium text-slate-900">{settings.data.provider}</span>
            {" · "}
            Model <span className="font-medium text-slate-900">{settings.data.model}</span>
          </p>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
            AI enabled
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={autoAnalysis}
              onChange={(event) => setAutoAnalysis(event.target.checked)}
            />
            Store auto-analysis preference (incoming messages are not analyzed automatically)
          </label>
          <TextField
            label="Temperature"
            name="temperature"
            value={temperature}
            onChange={(event) => setTemperature(event.target.value)}
          />
          <TextField
            label="Maximum reply length (tokens)"
            name="max_output_tokens"
            value={maxTokens}
            onChange={(event) => setMaxTokens(event.target.value)}
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={knowledgeEnabled}
              onChange={(event) => setKnowledgeEnabled(event.target.checked)}
            />
            Knowledge retrieval enabled
          </label>
          <TextField
            label="Knowledge top K"
            name="knowledge_top_k"
            value={knowledgeTopK}
            onChange={(event) => setKnowledgeTopK(event.target.value)}
          />
          <TextField
            label="Knowledge relevance threshold (cosine distance)"
            name="knowledge_max_distance"
            value={knowledgeDistance}
            onChange={(event) => setKnowledgeDistance(event.target.value)}
          />
          {error && <Alert tone="error">{error}</Alert>}
          {saved && <Alert tone="success">AI settings saved.</Alert>}
          <SubmitButton busy={saving}>Save AI settings</SubmitButton>
        </form>
      )}
    </section>
  );
}
