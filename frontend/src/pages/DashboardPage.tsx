import { Link } from "react-router";
import { useAuth } from "../auth/context";
import { useInstagramAccounts } from "../hooks/useInstagramAccounts";

export default function DashboardPage() {
  const { account, organization } = useAuth();
  const { accounts, loading, error } = useInstagramAccounts(organization?.id);
  const connected = accounts?.filter((a) => a.connection_status === "connected") ?? [];
  const firstName = account?.user.name?.split(" ")[0];

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold">Welcome{firstName ? `, ${firstName}` : ""}</h1>

      <div className="mt-8 grid gap-6 sm:grid-cols-2">
        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="text-sm font-medium text-slate-500">Organization</h2>
          {organization ? (
            <>
              <p className="mt-2 text-lg font-semibold">{organization.name}</p>
              <p className="mt-1 text-sm capitalize text-slate-600">Your role: {organization.role}</p>
            </>
          ) : (
            <p className="mt-2 text-sm text-slate-600">
              You're not a member of any organization. Ask an organization owner to invite you.
            </p>
          )}
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-slate-500">Instagram</h2>
            {accounts && (
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                  connected.length ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"
                }`}
              >
                {connected.length ? "Connected" : "Not connected"}
              </span>
            )}
          </div>
          {loading && <p className="mt-2 text-sm text-slate-500">Loading…</p>}
          {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
          {accounts && (
            <p className="mt-2 text-sm text-slate-600">
              {connected.length
                ? connected.map((a) => `@${a.username}`).join(", ")
                : "Connect an Instagram Business or Creator account to start receiving messages and comments."}
            </p>
          )}
          <Link to="/integrations" className="mt-4 inline-block text-sm font-medium text-brand-600 hover:underline">
            Manage integrations
          </Link>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="text-sm font-medium text-slate-500">Inbox</h2>
          <p className="mt-2 text-sm text-slate-600">
            Read Instagram conversations, update status, and see remembered customer details.
          </p>
          <Link to="/inbox" className="mt-4 inline-block text-sm font-medium text-brand-600 hover:underline">
            Open inbox
          </Link>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="text-sm font-medium text-slate-500">Customers</h2>
          <p className="mt-2 text-sm text-slate-600">
            Profiles and team-written memories for people who have messaged a connected account.
          </p>
          <Link to="/customers" className="mt-4 inline-block text-sm font-medium text-brand-600 hover:underline">
            View customers
          </Link>
        </section>
      </div>
    </div>
  );
}
