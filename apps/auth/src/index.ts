import { serve } from "@hono/node-server";
import { Hono } from "hono";
import { cors } from "hono/cors";

import { auth } from "./auth.js";

const trustedOrigins = (process.env.AUTH_TRUSTED_ORIGINS ?? "http://localhost:5173,http://localhost:8080")
  .split(",")
  .map((origin) => origin.trim())
  .filter((origin) => origin.length > 0);

const app = new Hono();

app.use(
  "/api/auth/*",
  cors({
    origin: (origin) => {
      if (!origin) {
        return trustedOrigins[0] ?? "";
      }
      return trustedOrigins.includes(origin) ? origin : null;
    },
    credentials: true,
    allowHeaders: ["Content-Type", "Authorization"],
    allowMethods: ["GET", "POST", "OPTIONS"],
  }),
);

app.get("/health", (c) => c.json({ status: "ok" }));

app.all("/api/auth/*", (c) => auth.handler(c.req.raw));

const port = Number(process.env.PORT ?? 3001);

serve(
  {
    fetch: app.fetch,
    hostname: "0.0.0.0",
    port,
  },
  (info) => {
    console.log(`auth listening on http://127.0.0.1:${info.port}`);
  },
);
