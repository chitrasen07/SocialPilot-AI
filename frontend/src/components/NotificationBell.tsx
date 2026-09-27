import { useState } from "react";
import { useAuth } from "../auth/context";
import { useApiQuery } from "../hooks/useApiQuery";
import { api } from "../lib/api";
import { formatDateTime } from "../lib/inbox";
import type { AppNotification } from "../types/api";

export default function NotificationBell() {
  const { organization } = useAuth();
  const [open, setOpen] = useState(false);
  const notes = useApiQuery<{ items: AppNotification[]; unread_count: number }>(
    organization ? "/api/notifications" : null,
    organization?.id,
  );
  const unread = notes.data?.unread_count ?? 0;

  async function markRead(id: string) {
    if (!organization) return;
    await api(`/api/notifications/${id}/read`, { method: "POST", organizationId: organization.id });
    notes.reload();
  }

  if (!organization) return null;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
        aria-expanded={open}
      >
        Notifications
        {unread > 0 && (
          <span className="ml-2 rounded-full bg-brand-600 px-1.5 py-0.5 text-xs text-white">{unread}</span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-2 w-80 rounded-xl border border-slate-200 bg-white p-3 shadow-lg">
          <p className="text-sm font-medium">Recent</p>
          {notes.data?.items.length === 0 && <p className="mt-2 text-sm text-slate-500">No notifications.</p>}
          <ul className="mt-2 max-h-80 space-y-2 overflow-auto">
            {notes.data?.items.map((item) => (
              <li key={item.id} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <p className="font-medium">{item.title}</p>
                <p className="text-slate-600">{item.message}</p>
                <p className="mt-1 text-xs text-slate-400">{formatDateTime(item.created_at)}</p>
                {!item.read && (
                  <button
                    type="button"
                    onClick={() => void markRead(item.id)}
                    className="mt-1 text-xs text-brand-600 hover:underline"
                  >
                    Mark read
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
