import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut as firebaseSignOut,
  updateProfile,
  type Auth,
  type User as FirebaseUser,
} from "firebase/auth";
import { ApiError, api } from "../lib/api";
import { firebaseAuth } from "../lib/firebase";
import type { MeResponse, SyncResponse } from "../types/api";
import { AuthContext, type Account, type AuthContextValue, type AuthStatus } from "./context";

const NOT_CONFIGURED = "Sign-in is not configured. Set the VITE_FIREBASE_* environment variables.";

function requireAuth(): Auth {
  if (!firebaseAuth) throw new Error(NOT_CONFIGURED);
  return firebaseAuth;
}

function verificationSettings() {
  return { url: `${window.location.origin}/verify-email` };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(firebaseAuth ? "loading" : "error");
  const [error, setError] = useState<string | null>(firebaseAuth ? null : NOT_CONFIGURED);
  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  // Ignores results from syncs superseded by a newer auth state change.
  const generation = useRef(0);

  const resolveUser = useCallback(async (user: FirebaseUser | null) => {
    const current = ++generation.current;
    setFirebaseUser(user);
    setError(null);
    if (!user) {
      setAccount(null);
      setStatus("unauthenticated");
      return;
    }
    if (!user.emailVerified) {
      setAccount(null);
      setStatus("unverified");
      return;
    }
    setStatus("loading");
    try {
      const synced = await api<SyncResponse>("/api/auth/sync", { method: "POST" });
      if (current !== generation.current) return;
      setAccount({ user: synced.user, organizations: synced.organizations, isNewUser: synced.is_new_user });
      setStatus("authenticated");
    } catch (err) {
      if (current !== generation.current) return;
      setAccount(null);
      setError(err instanceof ApiError ? err.message : "Sign-in could not be completed.");
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    if (!firebaseAuth) return;
    return onAuthStateChanged(firebaseAuth, (user) => void resolveUser(user));
  }, [resolveUser]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      loading: status === "loading",
      isAuthenticated: status === "authenticated",
      error,
      firebaseUser,
      account,
      organization: account?.organizations[0] ?? null,

      async signIn(email, password) {
        await signInWithEmailAndPassword(requireAuth(), email, password);
      },

      async signUp(name, email, password) {
        const { user } = await createUserWithEmailAndPassword(requireAuth(), email, password);
        await updateProfile(user, { displayName: name });
        await sendEmailVerification(user, verificationSettings());
      },

      async signInWithGoogle() {
        await signInWithPopup(requireAuth(), new GoogleAuthProvider());
      },

      async signOut() {
        await firebaseSignOut(requireAuth());
      },

      async resetPassword(email) {
        await sendPasswordResetEmail(requireAuth(), email, {
          url: `${window.location.origin}/signin`,
        });
      },

      async resendVerification() {
        const user = requireAuth().currentUser;
        if (user) await sendEmailVerification(user, verificationSettings());
      },

      async checkVerification() {
        const user = requireAuth().currentUser;
        if (!user) return false;
        await user.reload();
        if (!user.emailVerified) return false;
        // The cached ID token still says email_verified=false until it is refreshed.
        await user.getIdToken(true);
        await resolveUser(user);
        return true;
      },

      async refreshAccount() {
        const me = await api<MeResponse>("/api/me");
        setAccount({ ...me, isNewUser: false });
      },
    }),
    [status, error, firebaseUser, account, resolveUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
