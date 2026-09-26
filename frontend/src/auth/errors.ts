import { FirebaseError } from "firebase/app";

const FIREBASE_MESSAGES: Record<string, string> = {
  "auth/invalid-credential": "Incorrect email or password.",
  "auth/invalid-email": "Enter a valid email address.",
  "auth/email-already-in-use": "An account with this email already exists. Sign in instead.",
  "auth/weak-password": "Choose a stronger password (at least 8 characters).",
  "auth/too-many-requests": "Too many attempts. Wait a moment and try again.",
  "auth/network-request-failed": "Network error. Check your connection and try again.",
  "auth/popup-blocked": "Your browser blocked the Google sign-in window. Allow pop-ups and retry.",
  "auth/account-exists-with-different-credential":
    "This email is already registered with a different sign-in method.",
  "auth/user-disabled": "This account has been disabled.",
};

/** Firebase codes that mean the user dismissed the flow; not worth showing as an error. */
const DISMISSED = new Set(["auth/popup-closed-by-user", "auth/cancelled-popup-request"]);

export function authErrorMessage(err: unknown): string | null {
  if (err instanceof FirebaseError) {
    if (DISMISSED.has(err.code)) return null;
    return FIREBASE_MESSAGES[err.code] ?? "Something went wrong. Please try again.";
  }
  if (err instanceof Error) return err.message;
  return "Something went wrong. Please try again.";
}
