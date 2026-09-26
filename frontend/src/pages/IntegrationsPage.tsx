import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { useAuth } from "../auth/context";
import { Alert } from "../components/forms";
import { useInstagramAccounts } from "../hooks/useInstagramAccounts";
import { ApiError, api } from "../lib/api";
import type { InstagramAccount } from "../types/api";

const CALLBACK_ERRORS: Record<string, string> = {
  INSTAGRAM_AUTHORIZATION_DENIED: "Instagram authorization was cancelled.",
  OAUTH_STATE_INVALID: "The connection link expired. Please try again.",
  OAUTH_STATE_MISMATCH: "Finish connecting in the same browser you started from.",
  INSTAGRAM_ACCOUNT_IN_USE: "That Instagram account is already connected to another organization.",
  INSTAGRAM_CONNECTION_FAILED:
    "Instagram didn't complete the connection. Make sure it's a Business or Creator account and try again.",
  INSTAGRAM_WEBHOOK_SUBSCRIPTION_FAILED: "Connected, but event delivery couldn't be enabled. Please try again.",
  ORGANIZATION_ACCESS_DENIED: "You no longer have permission to manage this organization's integrations.",
  INSTAGRAM_NOT_CONFIGURED: "Instagram integration is not configured on this server.",
};

const STATUS_BADGE: Record<InstagramAccount["connection_status"], { label: string; className: string }> = {
  connected: { label: "Connected", className: "bg-emerald-50 text-emerald-700" },
  needs_reauth: { label: "Reconnect required", className: "bg-amber-50 text-amber-700" },
  disconnected: { label: "Disconnected", className: "bg-slate-100 text-slate-600" },
};

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

export default function IntegrationsPage() {
  const { organization } = useAuth();
  const { accounts, loading, error, reload } = useInstagramAccounts(organization?.id);
  const [searchParams, setSearchParams] = useSearchParams();
  const [notice, setNotice] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const canManage = organization?.role === "owner" || organization?.role === "admin";

  // Result of the OAuth round trip, passed back by the backend callback redirect.
  useEffect(() => {
    const connected = searchParams.get("instagram") === "connected";
    const errorCode = searchParams.get("instagram_error");
    if (!connected && !errorCode) return;
    setNotice(
      connected
        ? { tone: "success", text: "Instagram account connected." }
        : { tone: "error", text: CALLBACK_ERRORS[errorCode ?? ""] ?? "The connection could not be completed." },
    );
    setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams]);

  if (!organization) return null;
  const organizationId = organization.id;

  async function connect() {
    setBusy(true);
    setNotice(null);
    try {
      const { authorization_url } = await api<{ authorization_url: string }>("/api/instagram/connect", {
        method: "POST",
        organizationId,
      });
      window.location.assign(authorization_url);
    } catch (err) {
      setNotice({ tone: "error", text: err instanceof ApiError ? err.message : "Could not start the connection." });
      setBusy(false);
    }
  }

  async function disconnect(account: InstagramAccount) {
    if (!window.confirm(`Disconnect @${account.username}? SocialPilot will stop receiving its messages.`)) return;
    setBusy(true);
    setNotice(null);
    try {
      await api(`/api/instagram/accounts/${account.id}`, { method: "DELETE", organizationId });
      await reload();
      setNotice({ tone: "success", text: `@${account.username} disconnected.` });
    } catch (err) {
      setNotice({ tone: "error", text: err instanceof ApiError ? err.message : "Could not disconnect." });
    } finally {
      setBusy(false);
    }
  }

  const connectButton = canManage && (
    <button
      onClick={() => void connect()}
      disabled={busy}
      className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500 disabled:opacity-60"
    >
      {accounts?.length ? "Connect another account" : "Connect Instagram"}
    </button>
  );

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-semibold">Integrations</h1>
      <p className="mt-1 text-sm text-slate-600">
        Accounts are connected through Meta's official Instagram authorization. SocialPilot never asks for
        your Instagram password.
      </p>

      {notice && (
        <div className="mt-6">
          <Alert tone={notice.tone}>{notice.text}</Alert>
        </div>
      )}

      <section className="mt-6 rounded-xl border border-slate-200 bg-white">
        <header className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h2 className="font-semibold">Instagram</h2>
            <p className="text-sm text-slate-600">Business or Creator accounts</p>
          </div>
          {!loading && !error && connectButton}
        </header>

        <div className="px-6 py-5">
          {loading && <p className="text-sm text-slate-500">Loading…</p>}
          {error && <Alert tone="error">{error}</Alert>}
          {accounts?.length === 0 && (
            <p className="text-sm text-slate-600">
              Status: <span className="font-medium">Not connected</span>
              {!canManage && " — ask an owner or admin to connect an account."}
            </p>
          )}
          <ul className="divide-y divide-slate-100">
            {accounts?.map((account) => {
              const badge = STATUS_BADGE[account.connection_status];
              return (
                <li key={account.id} className="flex flex-wrap items-start justify-between gap-4 py-3 first:pt-0 last:pb-0">
                  <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
                    <dt className="text-slate-500">Account</dt>
                    <dd className="font-medium">@{account.username}</dd>
                    <dt className="text-slate-500">Account ID</dt>
                    <dd className="font-mono text-xs leading-5">{account.instagram_account_id}</dd>
                    <dt className="text-slate-500">Connected</dt>
                    <dd>{formatDate(account.connected_at)}</dd>
                    <dt className="text-slate-500">Last event</dt>
                    <dd>{formatDate(account.last_webhook_at)}</dd>
                  </dl>
                  <div className="flex items-center gap-3">
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.className}`}>
                      {badge.label}
                    </span>
                    {canManage && (
                      <button
                        onClick={() => void disconnect(account)}
                        disabled={busy}
                        className="text-sm text-red-600 hover:underline disabled:opacity-60"
                      >
                        Disconnect
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </section>
    </div>
  );
}
