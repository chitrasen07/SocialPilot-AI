import { Link } from "react-router";
import { useAuth } from "../auth/context";
import { Alert } from "../components/forms";
import { useApiQuery } from "../hooks/useApiQuery";
import type { AnalyticsCustomers, AnalyticsOverview, EngagementDashboard } from "../types/api";

function label(value: string) {
  return value.replaceAll("_", " ");
}

function Bars({ rows }: { rows: { label: string; value: number }[] }) {
  const max = Math.max(1, ...rows.map((row) => row.value));
  if (rows.length === 0) return <p className="mt-3 text-sm text-slate-500">Nothing to show yet.</p>;
  return (
    <ul className="mt-4 space-y-3">
      {rows.map((row) => (
        <li key={row.label}>
          <div className="flex justify-between text-xs text-slate-600">
            <span className="capitalize">{row.label}</span>
            <span>{row.value}</span>
          </div>
          <div className="mt-1 h-2 rounded bg-slate-100">
            <div className="h-2 rounded bg-brand-600" style={{ width: `${(row.value / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function Metric({ name, value }: { name: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
      <p className="text-xs text-slate-500">{name}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}

export default function AnalyticsPage() {
  const { organization } = useAuth();
  const overview = useApiQuery<AnalyticsOverview>("/api/analytics/overview", organization?.id);
  const customers = useApiQuery<AnalyticsCustomers>("/api/analytics/customers", organization?.id);
  const performance = useApiQuery<{ totals: AnalyticsOverview["totals"] }>(
    "/api/analytics/ai-performance",
    organization?.id,
  );
  const channels = useApiQuery<{
    channels: {
      channel: string;
      total_messages: number;
      total_conversations: number;
      ai_generated: number;
      approved: number;
      approval_rate: number;
      average_response_seconds: number | null;
    }[];
  }>("/api/analytics/channels", organization?.id);
  const intelligence = useApiQuery<EngagementDashboard>("/api/intelligence/dashboard", organization?.id);
  const error = overview.error || customers.error || performance.error || channels.error;
  const data = overview.data;

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Analytics</h1>
        <p className="mt-1 text-sm text-slate-600">
          Conversation volume, customer themes, and how drafts are reviewed. Drafts stay in the review queue.
        </p>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      {!data && !error && <p className="text-sm text-slate-500">Loading…</p>}
      {data && (
        <>
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric name="Conversations" value={data.totals.total_conversations} />
            <Metric name="Messages received" value={data.totals.total_messages} />
            <Metric name="AI drafts" value={data.totals.ai_generated} />
            <Metric
              name="Avg. response"
              value={
                data.average_response_seconds == null ? "—" : `${Math.round(data.average_response_seconds)}s`
              }
            />
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-white px-6 py-5">
              <h2 className="font-semibold">Conversation volume</h2>
              <Bars
                rows={data.days.map((day) => ({
                  label: day.day,
                  value: day.total_messages,
                }))}
              />
            </div>
            <div className="rounded-xl border border-slate-200 bg-white px-6 py-5">
              <h2 className="font-semibold">Customer sentiment</h2>
              <Bars rows={data.sentiment.map((item) => ({ label: item.sentiment, value: item.count }))} />
            </div>
            <div className="rounded-xl border border-slate-200 bg-white px-6 py-5">
              <h2 className="font-semibold">Top questions</h2>
              <Bars rows={data.top_questions.map((item) => ({ label: label(item.intent), value: item.count }))} />
            </div>
            <div className="rounded-xl border border-slate-200 bg-white px-6 py-5">
              <h2 className="font-semibold">Requested products</h2>
              <Bars rows={data.products.map((item) => ({ label: item.product, value: item.count }))} />
            </div>
            <div className="rounded-xl border border-slate-200 bg-white px-6 py-5">
              <h2 className="font-semibold">Common problems</h2>
              <Bars rows={data.problems.map((item) => ({ label: label(item.intent), value: item.count }))} />
            </div>
            <div className="rounded-xl border border-slate-200 bg-white px-6 py-5">
              <h2 className="font-semibold">AI performance</h2>
              <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                <p>Approval rate {Math.round((performance.data?.totals.approval_rate ?? 0) * 100)}%</p>
                <p>Approved {performance.data?.totals.approved ?? 0}</p>
                <p>Edited {performance.data?.totals.edited ?? 0}</p>
                <p>Rejected {performance.data?.totals.rejected ?? 0}</p>
                <p>Escalated {performance.data?.totals.escalated ?? 0}</p>
              </div>
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
            <h2 className="font-semibold">By channel</h2>
            {(channels.data?.channels.length ?? 0) === 0 && (
              <p className="mt-3 text-sm text-slate-500">No channel activity yet.</p>
            )}
            <ul className="mt-3 divide-y divide-slate-100 text-sm">
              {channels.data?.channels.map((item) => (
                <li key={item.channel} className="grid grid-cols-2 gap-2 py-3 capitalize sm:grid-cols-5">
                  <span className="font-medium">{item.channel === "webchat" ? "Website" : item.channel}</span>
                  <span>{item.total_messages} messages</span>
                  <span>{item.total_conversations} conversations</span>
                  <span>{Math.round(item.approval_rate * 100)}% approved</span>
                  <span>
                    {item.average_response_seconds == null
                      ? "No response time yet"
                      : `${Math.round(item.average_response_seconds)}s response`}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-semibold">Customer intelligence</h2>
              <Link to="/intelligence" className="text-sm text-brand-600 hover:underline">
                Open dashboard
              </Link>
            </div>
            <div className="mt-3 grid gap-3 text-sm sm:grid-cols-4">
              <p>Conversations {intelligence.data?.total_conversations ?? "—"}</p>
              <p>Qualified leads {intelligence.data?.qualified_leads ?? "—"}</p>
              <p>Average lead score {intelligence.data?.average_lead_score ?? "—"}</p>
              <p>AI improvement {Math.round((intelligence.data?.ai_improvement_score ?? 0) * 100)}%</p>
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
            <h2 className="font-semibold">Customer segments</h2>
            <Bars
              rows={(customers.data?.segments ?? []).map((item) => ({
                label: label(item.segment),
                value: item.customers,
              }))}
            />
          </section>
        </>
      )}
    </div>
  );
}
