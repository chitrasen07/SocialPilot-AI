import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../lib/api";
import type { InstagramAccount, ListResponse } from "../types/api";

export function useInstagramAccounts(organizationId: string | undefined) {
  const [accounts, setAccounts] = useState<InstagramAccount[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!organizationId) return;
    setError(null);
    try {
      const data = await api<ListResponse<InstagramAccount>>("/api/instagram/accounts", { organizationId });
      setAccounts(data.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load Instagram accounts.");
    }
  }, [organizationId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { accounts, loading: Boolean(organizationId) && accounts === null && error === null, error, reload };
}
