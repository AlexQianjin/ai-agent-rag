import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";
import { z } from "zod";

import { authClient, waitForSessionUser } from "../lib/auth-client";

const loginSchema = z.object({
  email: z.email("Enter a valid email"),
  password: z.string().min(8, "Use at least 8 characters"),
});

type LoginValues = z.infer<typeof loginSchema>;

export function LoginPage() {
  const navigate = useNavigate();
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    const { error } = await authClient.signIn.email(values);
    if (error) {
      form.setError("root", { message: error.message ?? "Could not log in." });
      return;
    }
    try {
      await waitForSessionUser();
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "The session did not start.";
      form.setError("root", { message });
      return;
    }
    await navigate("/users");
  });

  return (
    <form onSubmit={onSubmit} className="mx-auto max-w-md space-y-4" noValidate>
      <h1 className="text-2xl font-semibold tracking-tight">Log in</h1>
      <label className="block text-sm">
        Email
        <input
          type="email"
          className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2"
          {...form.register("email")}
        />
        <FieldError message={form.formState.errors.email?.message} />
      </label>
      <label className="block text-sm">
        Password
        <input
          type="password"
          className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2"
          {...form.register("password")}
        />
        <FieldError message={form.formState.errors.password?.message} />
      </label>
      {form.formState.errors.root ? <p className="text-sm text-red-400">{form.formState.errors.root.message}</p> : null}
      <button type="submit" className="rounded-md bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-950">
        Log in
      </button>
      <p className="text-sm text-zinc-400">
        Need an account?{" "}
        <Link to="/signup" className="text-zinc-100 underline">
          Sign up
        </Link>
      </p>
    </form>
  );
}

function FieldError({ message }: { message?: string }) {
  if (!message) {
    return null;
  }
  return <span className="mt-1 block text-red-400">{message}</span>;
}
