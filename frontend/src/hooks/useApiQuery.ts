import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../lib/api";

/** Loads `path` for the organization; pass a null path to skip. Stale responses are dropped. */
export function useApiQuery<T>(path: string | null, organizationId: string | undefined) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!path || !organizationId) return;
    let current = true;
    setLoading(true);
    setError(null);
    api<T>(path, { organizationId })
      .then((result) => current && setData(result))
      .catch((err: unknown) => {
        if (!current) return;
        setData(null);
        setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      })
      .finally(() => current && setLoading(false));
    return () => {
      current = false;
    };
  }, [path, organizationId, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { data, setData, error, loading, reload };
}
