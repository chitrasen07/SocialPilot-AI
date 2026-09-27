import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";
import { Alert, SubmitButton } from "./forms";
import { useApiQuery } from "../hooks/useApiQuery";
import { ApiError, api } from "../lib/api";
import { formatDateTime } from "../lib/inbox";
import type { AISettings } from "../types/api";

const PERSONALITIES: { id: AISettings["personality"]; title: string; description: string }[] = [
  { id: "professional", title: "Professional", description: "Calm and precise." },
  { id: "friendly", title: "Friendly", description: "Warm and plain-spoken." },
  { id: "casual", title: "Casual", description: "Relaxed and short." },
  { id: "premium", title: "Premium", description: "Polished, without hype." },
  { id: "playful", title: "Playful", description: "Light, and still appropriate." },
  { id: "custom", title: "Custom", description: "Use your own voice notes." },
];

export function BrandSettings({ organizationId }: { organizationId: string }) {
  const settings = useApiQuery<AISettings>("/api/ai/settings", organizationId);
  const [personality, setPersonality] = useState<AISettings["personality"]>("friendly");
  const [voice, setVoice] = useState("");
  const [instructions, setInstructions] = useState("");
  const [preferred, setPreferred] = useState<string[]>([]);
  const [forbidden, setForbidden] = useState<string[]>([]);
  const [emoji, setEmoji] = useState<AISettings["emoji_policy"]>("minimal");
  const [length, setLength] = useState<AISettings["response_length"]>("medium");
  const [language, setLanguage] = useState<AISettings["language_mode"]>("auto");
  const [refunds, setRefunds] = useState(true);
  const [payments, setPayments] = useState(true);
  const [highRisk, setHighRisk] = useState(true);
  const [unsupported, setUnsupported] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!settings.data) return;
    setPersonality(settings.data.personality);
    setVoice(settings.data.brand_voice);
    setInstructions(settings.data.custom_instructions);
    setPreferred(settings.data.preferred_terms);
    setForbidden(settings.data.forbidden_terms);
    setEmoji(settings.data.emoji_policy);
    setLength(settings.data.response_length);
    setLanguage(settings.data.language_mode);
    setRefunds(settings.data.require_review_for_refunds);
    setPayments(settings.data.require_review_for_payment_issues);
    setHighRisk(settings.data.require_review_for_high_risk);
    setUnsupported(settings.data.require_review_for_unsupported_claims);
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
          personality,
          brand_voice: voice,
          custom_instructions: instructions,
          preferred_terms: preferred,
          forbidden_terms: forbidden,
          emoji_policy: emoji,
          response_length: length,
          language_mode: language,
          require_review_for_refunds: refunds,
          require_review_for_payment_issues: payments,
          require_review_for_high_risk: highRisk,
          require_review_for_unsupported_claims: unsupported,
        },
      });
      setSaved(true);
      settings.reload();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not save brand settings.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
      <h2 className="font-semibold">AI Brand Control</h2>
      <p className="mt-1 text-sm text-slate-500">
        These rules shape drafts. They are not sent to Instagram, and they do not store API keys.
      </p>
      {settings.loading && !settings.data && <p className="mt-3 text-sm text-slate-500">Loading…</p>}
      {settings.error && (
        <div className="mt-3">
          <Alert tone="error">{settings.error}</Alert>
        </div>
      )}
      {settings.data && (
        <form onSubmit={(event) => void onSubmit(event)} className="mt-4 space-y-4">
          <fieldset>
            <legend className="text-sm font-medium text-slate-700">Personality</legend>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {PERSONALITIES.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={personality === item.id}
                  onClick={() => setPersonality(item.id)}
                  className={`rounded-lg border px-3 py-2 text-left text-sm ${
                    personality === item.id ? "border-slate-900 bg-slate-50" : "border-slate-200"
                  }`}
                >
                  <span className="font-medium">{item.title}</span>
                  <span className="mt-0.5 block text-slate-500">{item.description}</span>
                </button>
              ))}
            </div>
          </fieldset>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Brand voice</span>
            <textarea
              value={voice}
              maxLength={2000}
              rows={3}
              onChange={(event) => setVoice(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <span className="text-xs text-slate-500">{voice.length} / 2000</span>
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Custom instructions</span>
            <textarea
              value={instructions}
              maxLength={4000}
              rows={4}
              onChange={(event) => setInstructions(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <span className="text-xs text-slate-500">{instructions.length} / 4000</span>
          </label>
          <TermList label="Preferred terms" terms={preferred} onChange={setPreferred} />
          <TermList label="Forbidden terms" terms={forbidden} onChange={setForbidden} />
          <SelectField
            label="Emoji policy"
            value={emoji}
            onChange={setEmoji}
            options={[
              ["none", "None"],
              ["minimal", "Minimal"],
              ["moderate", "Moderate"],
              ["match_customer", "Match customer"],
            ]}
          />
          <SelectField
            label="Response length"
            value={length}
            onChange={setLength}
            options={[
              ["short", "Short"],
              ["medium", "Medium"],
              ["long", "Long"],
            ]}
          />
          <SelectField
            label="Language mode"
            value={language}
            onChange={setLanguage}
            options={[
              ["auto", "Automatic"],
              ["english", "English"],
              ["hindi", "Hindi"],
              ["hinglish", "Hinglish"],
              ["telugu", "Telugu"],
            ]}
          />
          <Check label="Require review for refunds" checked={refunds} onChange={setRefunds} />
          <Check label="Require review for payment issues" checked={payments} onChange={setPayments} />
          <Check label="Require review for high risk" checked={highRisk} onChange={setHighRisk} />
          <Check
            label="Require review for unsupported claims"
            checked={unsupported}
            onChange={setUnsupported}
          />
          {settings.data.updated_at && (
            <p className="text-xs text-slate-500">Last updated {formatDateTime(settings.data.updated_at)}</p>
          )}
          {error && <Alert tone="error">{error}</Alert>}
          {saved && <Alert tone="success">Brand settings saved.</Alert>}
          <SubmitButton busy={saving}>Save changes</SubmitButton>
        </form>
      )}
    </section>
  );
}

function TermList({
  label,
  terms,
  onChange,
}: {
  label: string;
  terms: string[];
  onChange: (terms: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  function add() {
    const term = draft.trim();
    if (!term || terms.some((item) => item.toLowerCase() === term.toLowerCase()) || terms.length >= 40) return;
    onChange([...terms, term.slice(0, 40)]);
    setDraft("");
  }

  function onKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      add();
    }
  }

  return (
    <div>
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <div className="mt-1 flex gap-2">
        <input
          value={draft}
          maxLength={40}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKey}
          aria-label={label}
          className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
        <button type="button" onClick={add} className="rounded-lg border border-slate-300 px-3 text-sm">
          Add
        </button>
      </div>
      <ul className="mt-2 flex flex-wrap gap-2">
        {terms.map((term) => (
          <li key={term}>
            <button
              type="button"
              onClick={() => onChange(terms.filter((item) => item !== term))}
              className="rounded-full bg-slate-100 px-2 py-1 text-xs"
            >
              {term} <span className="sr-only">Remove {term}</span>
              <span aria-hidden="true">×</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SelectField<T extends string>({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: T;
  onChange: (value: T) => void;
  options: [T, string][];
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as T)}
        className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
      >
        {options.map(([id, name]) => (
          <option key={id} value={id}>
            {name}
          </option>
        ))}
      </select>
    </label>
  );
}

function Check({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      {label}
    </label>
  );
}
