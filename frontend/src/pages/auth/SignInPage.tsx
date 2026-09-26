import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { useAuth } from "../../auth/context";
import { authErrorMessage } from "../../auth/errors";
import GoogleButton from "../../components/GoogleButton";
import { Alert, SubmitButton, TextField } from "../../components/forms";
import AuthLayout from "../../layouts/AuthLayout";

export default function SignInPage() {
  const { signIn, error: authError } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await signIn(String(form.get("email")), String(form.get("password")));
    } catch (err) {
      setError(authErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Welcome back to SocialPilot AI."
      footer={
        <>
          New to SocialPilot AI?{" "}
          <Link to="/signup" className="font-medium text-brand-600 hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      {(error ?? authError) && (
        <div className="mb-4">
          <Alert tone="error">{error ?? authError}</Alert>
        </div>
      )}
      <GoogleButton onError={setError} />
      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
        <TextField label="Email" name="email" type="email" autoComplete="email" required />
        <TextField label="Password" name="password" type="password" autoComplete="current-password" required />
        <div className="text-right">
          <Link to="/forgot-password" className="text-sm text-brand-600 hover:underline">
            Forgot password?
          </Link>
        </div>
        <SubmitButton busy={busy}>Sign in</SubmitButton>
      </form>
    </AuthLayout>
  );
}
