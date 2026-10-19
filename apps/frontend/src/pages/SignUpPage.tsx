import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";
import { z } from "zod";

import { authClient, waitForSessionUser } from "../lib/auth-client";

const signUpSchema = z.object({
  name: z.string().min(1, "Name is required"),
  email: z.email("Enter a valid email"),
  password: z.string().min(8, "Use at least 8 characters"),
});

type SignUpValues = z.infer<typeof signUpSchema>;

export function SignUpPage() {
  const navigate = useNavigate();
  const form = useForm<SignUpValues>({
    resolver: zodResolver(signUpSchema),
    defaultValues: { name: "", email: "", password: "" },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    const { error } = await authClient.signUp.email(values);
    if (error) {
      form.setError("root", { message: error.message ?? "Could not create the account." });
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
      <h1 className="text-2xl font-semibold tracking-tight">Sign up</h1>
      <label className="block text-sm">
        Name
        <input className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2" {...form.register("name")} />
        <FieldError message={form.formState.errors.name?.message} />
      </label>
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
        Create account
      </button>
      <p className="text-sm text-zinc-400">
        Already have an account?{" "}
        <Link to="/login" className="text-zinc-100 underline">
          Log in
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
