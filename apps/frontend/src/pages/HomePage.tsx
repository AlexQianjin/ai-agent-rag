import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { apiBaseUrl, authClient } from "../lib/auth-client";

export function HomePage() {
  const { data: session, isPending } = authClient.useSession();
  const me = useQuery({
    queryKey: ["me", session?.user.id],
    enabled: Boolean(session),
    retry: false,
    queryFn: async () => {
      const response = await fetch(`${apiBaseUrl}/me`, { credentials: "include" });
      if (!response.ok) {
        throw new Error("The API did not accept this session.");
      }
      return (await response.json()) as { id: string; email: string; name: string; role: string | null };
    },
  });

  return (
    <div className="max-w-xl">
      <h1 className="text-3xl font-semibold tracking-tight">Q&A with RAG</h1>
      <p className="mt-3 text-zinc-400">Sign in to manage users. Account data is stored with Better Auth.</p>
      {isPending ? <p className="mt-6 text-sm text-zinc-400">Checking your session…</p> : null}
      {session ? (
        <div className="mt-6 space-y-2 text-sm">
          <p>
            Signed in as <span className="text-zinc-100">{session.user.email}</span>
          </p>
          <p className="text-zinc-400">
            API session:{" "}
            {me.isLoading ? "checking…" : me.isError ? "not accepted" : (me.data?.role ?? "user")}
          </p>
          <Link to="/users" className="inline-block text-zinc-100 underline">
            Open users
          </Link>
        </div>
      ) : (
        <div className="mt-6 flex gap-4 text-sm">
          <Link to="/login" className="underline">
            Log in
          </Link>
          <Link to="/signup" className="underline">
            Sign up
          </Link>
        </div>
      )}
    </div>
  );
}
