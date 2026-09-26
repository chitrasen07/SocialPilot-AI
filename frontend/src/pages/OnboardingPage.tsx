import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router";
import { useAuth } from "../auth/context";
import { Alert, SubmitButton, TextField } from "../components/forms";
import { ApiError, api } from "../lib/api";
import type { Organization } from "../types/api";

export default function OnboardingPage() {
  const { organization, refreshAccount } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!organization || !["owner", "admin"].includes(organization.role)) {
    return <Navigate to="/dashboard" replace />;
  }
  const organizationId = organization.id;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name")).trim();
    setBusy(true);
    setError(null);
    try {
      await api<Organization>(`/api/organizations/${organizationId}`, { method: "PATCH", body: { name } });
      await refreshAccount();
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save your workspace name.");
      setBusy(false);
    }
  }

  return (
    <div className="max-w-md">
      <h1 className="text-2xl font-semibold">Set up your workspace</h1>
      <p className="mt-2 text-sm text-slate-600">
        Your workspace holds your Instagram accounts, conversations and team. You can rename it later.
      </p>
      <form onSubmit={(e) => void handleSubmit(e)} className="mt-8 space-y-4 rounded-xl border border-slate-200 bg-white p-6">
        {error && <Alert tone="error">{error}</Alert>}
        <TextField label="Workspace name" name="name" defaultValue={organization.name} required maxLength={100} />
        <SubmitButton busy={busy}>Continue</SubmitButton>
      </form>
    </div>
  );
}
