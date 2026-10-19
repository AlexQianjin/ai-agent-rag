import { useEffect } from "react";
import { useNavigate } from "react-router";

import { authClient } from "../lib/auth-client";

export function LogoutPage() {
  const navigate = useNavigate();

  useEffect(() => {
    void authClient.signOut().finally(() => {
      void navigate("/login", { replace: true });
    });
  }, [navigate]);

  return <p className="text-sm text-zinc-400">Signing out…</p>;
}
