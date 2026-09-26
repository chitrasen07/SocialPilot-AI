import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router";
import { useAuth } from "./context";

function FullScreenMessage({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <main className="grid min-h-screen place-items-center px-6">
      <div className="max-w-md text-center">
        <p className="font-medium text-slate-900">{title}</p>
        {body && <p className="mt-2 text-sm text-slate-600">{body}</p>}
        {action && <div className="mt-6">{action}</div>}
      </div>
    </main>
  );
}

function AuthError() {
  const { error, firebaseUser, signOut } = useAuth();
  return (
    <FullScreenMessage
      title="We couldn't complete sign-in"
      body={error ?? undefined}
      action={
        <div className="flex justify-center gap-3">
          <button
            onClick={() => window.location.reload()}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500"
          >
            Try again
          </button>
          {firebaseUser && (
            <button
              onClick={() => void signOut()}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100"
            >
              Sign out
            </button>
          )}
        </div>
      }
    />
  );
}

/** Renders child routes only once the backend has confirmed the session. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();

  switch (status) {
    case "loading":
      return <FullScreenMessage title="Loading your workspace…" />;
    case "error":
      return <AuthError />;
    case "unverified":
      return <Navigate to="/verify-email" replace />;
    case "unauthenticated":
      return <Navigate to="/signin" replace state={{ from: location.pathname }} />;
    case "authenticated":
      return <Outlet />;
  }
}

/** Sign-in/sign-up pages: bounce signed-in users into the app. */
export function PublicOnly() {
  const { status, account } = useAuth();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;

  if (status === "loading") return <FullScreenMessage title="Loading…" />;
  if (status === "unverified") return <Navigate to="/verify-email" replace />;
  if (status === "authenticated") {
    return <Navigate to={account?.isNewUser ? "/onboarding" : (from ?? "/dashboard")} replace />;
  }
  // "error" falls through so the pages can show the configuration/backend message inline.
  return <Outlet />;
}

export function RequireUnverified() {
  const { status } = useAuth();
  if (status === "loading") return <FullScreenMessage title="Loading…" />;
  if (status === "unverified") return <Outlet />;
  return <Navigate to={status === "authenticated" ? "/dashboard" : "/signin"} replace />;
}
