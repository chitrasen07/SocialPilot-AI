import { signOut } from "firebase/auth";
import { firebaseAuth } from "./firebase";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string | null,
  ) {
    super(message);
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  form?: FormData;
  organizationId?: string;
}

async function send(path: string, options: RequestOptions, forceRefresh: boolean) {
  const headers: Record<string, string> = {};
  const token = await firebaseAuth?.currentUser?.getIdToken(forceRefresh);
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.organizationId) headers["X-Organization-Id"] = options.organizationId;
  let body: BodyInit | undefined;
  if (options.form) {
    body = options.form;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  return fetch(path, {
    method: options.method ?? "GET",
    headers,
    body,
  });
}

async function toApiError(response: Response): Promise<ApiError> {
  const requestId = response.headers.get("x-request-id");
  try {
    const { error } = (await response.json()) as { error: { code: string; message: string } };
    return new ApiError(response.status, error.code, error.message, requestId);
  } catch {
    return new ApiError(
      response.status,
      "NETWORK_ERROR",
      "The server could not be reached. Try again shortly.",
      requestId,
    );
  }
}

/** Calls the SocialPilot API with the current Firebase ID token attached. */
export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response: Response;
  try {
    response = await send(path, options, false);
    // A rejected token may just be stale (e.g. email verified since it was issued): refresh once.
    if (response.status === 401 && firebaseAuth?.currentUser) {
      response = await send(path, options, true);
      if (response.status === 401) await signOut(firebaseAuth);
    }
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "The server could not be reached. Try again shortly.", null);
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
