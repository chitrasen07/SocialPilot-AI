import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { useAuth } from "../../auth/context";
import { authErrorMessage } from "../../auth/errors";
import GoogleButton from "../../components/GoogleButton";
import { Alert, SubmitButton, TextField } from "../../components/forms";
import AuthLayout from "../../layouts/AuthLayout";

const MIN_PASSWORD_LENGTH = 8;

export default function SignUpPage() {
  const { signUp, error: authError } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name")).trim();
    const password = String(form.get("password"));

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (password !== form.get("confirmPassword")) {
      setError("Passwords do not match.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await signUp(name, String(form.get("email")), password);
    } catch (err) {
      setError(authErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Start managing Instagram conversations with AI."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/signin" className="font-medium text-brand-600 hover:underline">
            Sign in
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
        <TextField label="Name" name="name" autoComplete="name" required maxLength={200} />
        <TextField label="Email" name="email" type="email" autoComplete="email" required />
        <TextField
          label="Password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD_LENGTH}
        />
        <TextField
          label="Confirm password"
          name="confirmPassword"
          type="password"
          autoComplete="new-password"
          required
        />
        <SubmitButton busy={busy}>Create account</SubmitButton>
      </form>
    </AuthLayout>
  );
}
