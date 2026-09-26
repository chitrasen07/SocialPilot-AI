import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { useAuth } from "../../auth/context";
import { authErrorMessage } from "../../auth/errors";
import { Alert, SubmitButton, TextField } from "../../components/forms";
import AuthLayout from "../../layouts/AuthLayout";

export default function ForgotPasswordPage() {
  const { resetPassword } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = String(new FormData(event.currentTarget).get("email"));
    setBusy(true);
    setError(null);
    try {
      await resetPassword(email);
      setSent(true);
    } catch (err) {
      setError(authErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="We'll email you a link to choose a new password."
      footer={
        <Link to="/signin" className="font-medium text-brand-600 hover:underline">
          Back to sign in
        </Link>
      }
    >
      {sent ? (
        // Same message whether or not the account exists, to avoid revealing registered emails.
        <Alert tone="success">If an account exists for that email, a reset link is on its way.</Alert>
      ) : (
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          {error && <Alert tone="error">{error}</Alert>}
          <TextField label="Email" name="email" type="email" autoComplete="email" required />
          <SubmitButton busy={busy}>Send reset link</SubmitButton>
        </form>
      )}
    </AuthLayout>
  );
}
