import { createAuthClient } from "better-auth/react";
import { adminClient } from "better-auth/client/plugins";

export const authBaseUrl = import.meta.env.VITE_AUTH_URL ?? "http://localhost:5173";
// Empty means the page origin. Vite and nginx proxy these paths to FastAPI.
export const apiBaseUrl = import.meta.env.VITE_API_URL ?? "";

/** Document routes on the API. Same-origin pages use `/api/documents` so the SPA can own `/documents`. */
export function documentsApiUrl(path = ""): string {
  if (apiBaseUrl) {
    return `${apiBaseUrl}/documents${path}`;
  }
  return `/api/documents${path}`;
}

/** Retrieval route. Same-origin pages use `/api/search` so it is not a page path. */
export function searchApiUrl(): string {
  if (apiBaseUrl) {
    return `${apiBaseUrl}/search`;
  }
  return "/api/search";
}

export const authClient = createAuthClient({
  baseURL: authBaseUrl,
  plugins: [adminClient()],
});

type SessionAtomState = {
  data: { user?: { id?: string } } | null;
};

/**
 * Sign-up and sign-in update the session atom on a short timer. Navigating
 * before that timer runs makes the users page treat the visitor as signed out.
 */
export function waitForSessionUser(): Promise<void> {
  const sessionAtom = authClient.$store.atoms.session as {
    subscribe: (listener: (state: SessionAtomState) => void) => () => void;
  };
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      unsubscribe();
      reject(new Error("The session did not start."));
    }, 5000);
    let unsubscribe = () => {};
    unsubscribe = sessionAtom.subscribe((state) => {
      if (!state.data?.user) {
        return;
      }
      window.clearTimeout(timeout);
      queueMicrotask(() => unsubscribe());
      resolve();
    });
  });
}
