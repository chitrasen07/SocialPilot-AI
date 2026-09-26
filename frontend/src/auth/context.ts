import { createContext, useContext } from "react";
import type { User as FirebaseUser } from "firebase/auth";
import type { MeResponse, Organization } from "../types/api";

export type AuthStatus = "loading" | "unauthenticated" | "unverified" | "authenticated" | "error";

export interface Account extends MeResponse {
  isNewUser: boolean;
}

export interface AuthContextValue {
  status: AuthStatus;
  loading: boolean;
  isAuthenticated: boolean;
  /** Set when status is "error" (e.g. backend unreachable or Firebase not configured). */
  error: string | null;
  firebaseUser: FirebaseUser | null;
  account: Account | null;
  /** The active organization. Until an organization switcher exists, the user's first one. */
  organization: Organization | null;
  signIn(email: string, password: string): Promise<void>;
  signUp(name: string, email: string, password: string): Promise<void>;
  signInWithGoogle(): Promise<void>;
  signOut(): Promise<void>;
  resetPassword(email: string): Promise<void>;
  resendVerification(): Promise<void>;
  /** Re-checks email verification and completes sign-in when verified. */
  checkVerification(): Promise<boolean>;
  refreshAccount(): Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
