import { betterAuth } from "better-auth";
import { admin } from "better-auth/plugins";
import { Pool } from "pg";

import { loadRootEnv } from "./load-env.js";

loadRootEnv();

function requiredEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

const secret = requiredEnv("BETTER_AUTH_SECRET");
if (secret.length < 32) {
  throw new Error("BETTER_AUTH_SECRET must be at least 32 characters");
}

const baseURL = requiredEnv("BETTER_AUTH_URL");
const databaseUrl = requiredEnv("DATABASE_URL");
const trustedOrigins = (process.env.AUTH_TRUSTED_ORIGINS ?? "http://localhost:5173,http://localhost:8080")
  .split(",")
  .map((origin) => origin.trim())
  .filter((origin) => origin.length > 0);

export const authOptions = {
  database: new Pool({ connectionString: databaseUrl }),
  secret,
  baseURL,
  trustedOrigins,
  emailAndPassword: {
    enabled: true,
  },
  advanced: {
    useSecureCookies: baseURL.startsWith("https://"),
  },
  plugins: [admin()],
};

export const auth = betterAuth(authOptions);
