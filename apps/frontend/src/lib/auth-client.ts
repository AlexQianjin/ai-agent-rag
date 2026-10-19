import { createAuthClient } from "better-auth/react";
import { adminClient } from "better-auth/client/plugins";

export const authBaseUrl = import.meta.env.VITE_AUTH_URL ?? "http://localhost:5173";
// Empty means the page origin. Vite and nginx proxy these paths to FastAPI.
export const apiBaseUrl = import.meta.env.VITE_API_URL ?? "";

export const authClient = createAuthClient({
  baseURL: authBaseUrl,
  plugins: [adminClient()],
});
