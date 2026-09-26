import { useEffect, useState } from "react";
import { useAuth } from "../../auth/context";
import { authErrorMessage } from "../../auth/errors";
import { Alert } from "../../components/forms";
import AuthLayout from "../../layouts/AuthLayout";

export default function VerifyEmailPage() {
  const { firebaseUser, checkVerification, resendVerification, signOut } = useAuth();
  const [message, setMessage] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  // Users usually verify in another tab; re-check when they come back to this one.
  useEffect(() => {
    const onFocus = () => void checkVerification().catch(() => undefined);
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [checkVerification]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
    } catch (err) {
      setMessage({ tone: "error", text: authErrorMessage(err) ?? "Something went wrong." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Verify your email"
      subtitle={`We sent a verification link to ${firebaseUser?.email ?? "your email address"}.`}
    >
      <div className="space-y-4">
        {message && <Alert tone={message.tone}>{message.text}</Alert>}
        <button
          disabled={busy}
          onClick={() =>
            void run(async () => {
              if (!(await checkVerification())) {
                setMessage({ tone: "error", text: "Your email isn't verified yet. Check your inbox." });
              }
            })
          }
          className="w-full rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-500 disabled:opacity-60"
        >
          I've verified my email
        </button>
        <button
          disabled={busy}
          onClick={() =>
            void run(async () => {
              await resendVerification();
              setMessage({ tone: "success", text: "Verification email sent." });
            })
          }
          className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium hover:bg-slate-50 disabled:opacity-60"
        >
          Resend email
        </button>
        <button
          onClick={() => void signOut()}
          className="w-full text-sm text-slate-600 hover:text-slate-900"
        >
          Use a different account
        </button>
      </div>
    </AuthLayout>
  );
}
