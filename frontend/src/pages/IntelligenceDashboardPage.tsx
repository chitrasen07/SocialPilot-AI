import { Link } from "react-router";
import { useAuth } from "../auth/context";
import { Alert } from "../components/forms";
import { useApiQuery } from "../hooks/useApiQuery";
import type { EngagementDashboard } from "../types/api";

function label(value: string) {
  return value.replaceAll("_", " ");
}

export default function IntelligenceDashboardPage() {
  const { organization } = useAuth();
  const dashboard = useApiQuery<EngagementDashboard>("/api/intelligence/dashboard", organization?.id);
  const data = dashboard.data;

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Customer intelligence</h1>
        <p className="mt-1 text-sm text-slate-600">
          Conversation stage, lead score, and how reviewed drafts perform. Drafts stay in the review queue.
        </p>
      </div>
      {dashboard.error && <Alert tone="error">{dashboard.error}</Alert>}
      {!data && !dashboard.error && <p className="text-sm text-slate-500">Loading…</p>}
      {data && (
        <>
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric name="Conversations" value={data.total_conversations} />
            <Metric name="Qualified leads" value={data.qualified_leads} />
            <Metric name="Average lead score" value={data.average_lead_score ?? "—"} />
            <Metric name="AI improvement" value={`${Math.round(data.ai_improvement_score * 100)}%`} />
          </section>

          <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
            <h2 className="font-semibold">Conversion funnel</h2>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
              {data.funnel.map((item) => (
                <li key={item.stage} className="flex justify-between text-sm capitalize">
                  <span>{label(item.stage)}</span>
                  <span>{item.customers}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-white px-6 py-5">
              <h2 className="font-semibold">Top intents</h2>
              <Simple rows={data.top_intents.map((item) => ({ label: label(item.intent), value: item.count }))} />
            </div>
            <div className="rounded-xl border border-slate-200 bg-white px-6 py-5">
              <h2 className="font-semibold">Top products</h2>
              <Simple rows={data.top_products.map((item) => ({ label: item.product, value: item.count }))} />
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
            <h2 className="font-semibold">Churn risk</h2>
            {data.churn_risk_customers.length === 0 && (
              <p className="mt-3 text-sm text-slate-500">No elevated churn risk from recent conversations.</p>
            )}
            <ul className="mt-3 divide-y divide-slate-100 text-sm">
              {data.churn_risk_customers.map((item) => (
                <li key={item.customer_id} className="flex justify-between py-2">
                  <Link to={`/customers/${item.customer_id}`} className="text-brand-600 hover:underline">
                    {item.display_name || "Customer"}
                  </Link>
                  <span>{Math.round(item.churn_probability * 100)}%</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white px-6 py-5">
            <h2 className="font-semibold">What review feedback favors</h2>
            <dl className="mt-3 grid grid-cols-[12rem_1fr] gap-y-1.5 text-sm">
              <dt className="text-slate-500">Accepted drafts</dt>
              <dd>{data.learning.accepted}</dd>
              <dt className="text-slate-500">Edited drafts</dt>
              <dd>{data.learning.edited}</dd>
              <dt className="text-slate-500">Rejected drafts</dt>
              <dd>{data.learning.rejected}</dd>
              <dt className="text-slate-500">Personality</dt>
              <dd className="capitalize">{data.learning.best_personality ?? "—"}</dd>
              <dt className="text-slate-500">Response length</dt>
              <dd className="capitalize">{data.learning.best_response_length ?? "—"}</dd>
              <dt className="text-slate-500">Language style</dt>
              <dd className="capitalize">{data.learning.best_language_style ?? "—"}</dd>
              <dt className="text-slate-500">Emoji usage</dt>
              <dd className="capitalize">{data.learning.best_emoji_usage ?? "—"}</dd>
            </dl>
          </section>
        </>
      )}
    </div>
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

function Simple({ rows }: { rows: { label: string; value: number }[] }) {
  if (rows.length === 0) return <p className="mt-3 text-sm text-slate-500">Nothing to show yet.</p>;
  return (
    <ul className="mt-3 space-y-2 text-sm">
      {rows.map((row) => (
        <li key={row.label} className="flex justify-between capitalize">
          <span>{row.label}</span>
          <span>{row.value}</span>
        </li>
      ))}
    </ul>
  );
}
