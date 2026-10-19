import { Link, Outlet } from "react-router";

import { authClient } from "../lib/auth-client";

export function Layout() {
  const { data: session } = authClient.useSession();

  return (
    <div className="min-h-svh bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4">
          <Link to="/" className="font-semibold tracking-tight">
            ai-agent-rag
          </Link>
          <nav className="flex items-center gap-4 text-sm text-zinc-300">
            {session ? (
              <>
                <Link to="/documents">Documents</Link>
                <Link to="/users">Users</Link>
                <Link to="/logout">Log out</Link>
              </>
            ) : (
              <>
                <Link to="/login">Log in</Link>
                <Link to="/signup">Sign up</Link>
              </>
            )}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-10">
        <Outlet />
      </main>
    </div>
  );
}
