import { useState } from "react";
import { Link } from "react-router";
import { useAuth } from "../auth/context";
import { Alert } from "../components/forms";
import { useApiQuery } from "../hooks/useApiQuery";
import { ApiError, api } from "../lib/api";
import { canManageInbox, formatDateTime } from "../lib/inbox";
import type { ListResponse, TaskStatus, WorkTask } from "../types/api";

const FILTERS = [
  ["open", "Open"],
  ["high", "High priority"],
  ["mine", "Assigned to me"],
] as const;

export default function TasksPage() {
  const { organization } = useAuth();
  const [filter, setFilter] = useState<(typeof FILTERS)[number][0]>("open");
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canUpdate = canManageInbox(organization?.role);
  const query =
    filter === "open" ? "status=open" : filter === "high" ? "priority=high" : "assigned=me";
  const tasks = useApiQuery<ListResponse<WorkTask>>(
    organization ? `/api/tasks?${query}` : null,
    organization?.id,
  );
  const current = tasks.data?.items.find((item) => item.id === selected) ?? tasks.data?.items[0] ?? null;

  async function setStatus(task: WorkTask, status: TaskStatus) {
    if (!organization) return;
    setError(null);
    try {
      await api(`/api/tasks/${task.id}`, {
        method: "PATCH",
        organizationId: organization.id,
        body: { status },
      });
      tasks.reload();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not update the task.");
    }
  }

  return (
    <div className="max-w-4xl space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Tasks</h1>
        <p className="mt-1 text-sm text-slate-600">Follow-ups for your team. Completing a task does not message Instagram.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {FILTERS.map(([id, label]) => (
          <button
            key={id}
            type="button"
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
      {tasks.error && <Alert tone="error">{tasks.error}</Alert>}
      <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
          {tasks.data?.items.length === 0 && <li className="px-4 py-6 text-sm text-slate-500">No tasks in this view.</li>}
          {tasks.data?.items.map((task) => (
            <li key={task.id}>
              <button
                type="button"
                onClick={() => setSelected(task.id)}
                className={`block w-full px-4 py-3 text-left text-sm ${current?.id === task.id ? "bg-slate-50" : ""}`}
              >
                <p className="font-medium">{task.title}</p>
                <p className="text-xs capitalize text-slate-500">
                  {task.status.replaceAll("_", " ")} · {task.priority}
                </p>
              </button>
            </li>
          ))}
        </ul>
        {current && (
          <section className="rounded-xl border border-slate-200 bg-white px-5 py-4">
            <h2 className="font-semibold">{current.title}</h2>
            <p className="mt-2 text-sm text-slate-600">{current.description || "No description."}</p>
            <p className="mt-2 text-xs text-slate-500">Opened {formatDateTime(current.created_at)}</p>
            {current.conversation_id && (
              <Link to={`/inbox?c=${current.conversation_id}`} className="mt-2 inline-block text-sm text-brand-600 hover:underline">
                Open conversation
              </Link>
            )}
            {canUpdate && (
              <div className="mt-4 flex flex-wrap gap-2">
                {(["open", "in_progress", "completed", "cancelled"] as const).map((status) => (
                  <button
                    key={status}
                    type="button"
                    onClick={() => void setStatus(current, status)}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm capitalize hover:bg-slate-50"
                  >
                    {status.replaceAll("_", " ")}
                  </button>
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
