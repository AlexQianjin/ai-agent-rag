import { Link, Outlet, useLocation } from "react-router";

import { authClient } from "../lib/auth-client";

export function Layout() {
  const { data: session } = authClient.useSession();
  const location = useLocation();
  const chat = location.pathname === "/chat" || location.pathname.startsWith("/chat/");

  return (
    <div className="flex min-h-svh flex-col bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800">
        <div className={`flex items-center justify-between px-4 py-4 ${chat ? "" : "mx-auto max-w-4xl"}`}>
          <Link to="/" className="font-semibold tracking-tight">
            ai-agent-rag
          </Link>
          <nav className="flex items-center gap-4 text-sm text-zinc-300">
            {session ? (
              <>
                <Link to="/chat">Chat</Link>
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
      <main className={chat ? "flex min-h-0 flex-1 flex-col" : "mx-auto w-full max-w-4xl flex-1 px-4 py-10"}>
        <Outlet />
      </main>
    </div>
  );
}
