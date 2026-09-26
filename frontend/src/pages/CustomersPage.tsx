import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../auth/context";
import { Alert } from "../components/forms";
import { useApiQuery } from "../hooks/useApiQuery";
import { formatDateTime } from "../lib/inbox";
import type { CustomerListItem, PageResponse } from "../types/api";

const PAGE_SIZE = 25;

export default function CustomersPage() {
  const { organization } = useAuth();
  const navigate = useNavigate();
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(input.trim());
      setOffset(0);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [input]);

  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  if (search) query.set("search", search);
  const { data, error, loading } = useApiQuery<PageResponse<CustomerListItem>>(
    `/api/customers?${query.toString()}`,
    organization?.id,
  );

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-semibold">Customers</h1>
      <p className="mt-1 text-sm text-slate-600">People who have messaged your connected Instagram accounts.</p>

      <input
        type="search"
        value={input}
        onChange={(event) => setInput(event.target.value)}
        placeholder="Search by username, name or Instagram ID"
        maxLength={100}
        className="mt-6 w-full max-w-md rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
      />

      {error && (
        <div className="mt-4">
          <Alert tone="error">{error}</Alert>
        </div>
      )}

      <div className="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">Username</th>
              <th className="px-4 py-3 font-medium">Display name</th>
              <th className="px-4 py-3 font-medium">Last interaction</th>
              <th className="px-4 py-3 text-right font-medium">Conversations</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data?.items.map((customer) => (
              <tr
                key={customer.id}
                onClick={() => void navigate(`/customers/${customer.id}`)}
                className="cursor-pointer hover:bg-slate-50"
              >
                <td className="px-4 py-3 font-medium">
                  {customer.username ? (
                    `@${customer.username}`
                  ) : (
                    <span className="font-mono text-xs text-slate-500">{customer.instagram_user_id}</span>
                  )}
                </td>
                <td className="px-4 py-3">{customer.display_name ?? "—"}</td>
                <td className="px-4 py-3 text-slate-600">{formatDateTime(customer.last_message_at)}</td>
                <td className="px-4 py-3 text-right">{customer.conversation_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && !data && <p className="px-4 py-6 text-sm text-slate-500">Loading…</p>}
        {data?.items.length === 0 && (
          <p className="px-4 py-6 text-sm text-slate-500">
            {search ? "No customers match your search." : "No customers yet."}
          </p>
        )}
      </div>

      {(offset > 0 || data?.has_more) && (
        <div className="mt-4 flex justify-end gap-3 text-sm">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            className="rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40"
          >
            Previous
          </button>
          <button
            disabled={!data?.has_more}
            onClick={() => setOffset(offset + PAGE_SIZE)}
            className="rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
