import { initializeApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

/** Null when the VITE_FIREBASE_* variables are not set; the auth UI reports this. */
export const firebaseAuth: Auth | null = Object.values(config).every(Boolean)
  ? getAuth(initializeApp(config))
  : null;
