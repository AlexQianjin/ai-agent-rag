import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Navigate } from "react-router";
import { z } from "zod";

import { authClient } from "../lib/auth-client";

const createUserSchema = z.object({
  name: z.string().min(1, "Name is required"),
  email: z.email("Enter a valid email"),
  password: z.string().min(8, "Use at least 8 characters"),
  role: z.enum(["user", "admin"]),
});

type CreateUserValues = z.infer<typeof createUserSchema>;

type ManagedUser = {
  id: string
  name: string
  email: string
  role?: string | null
};

export function UsersPage() {
  const { data: session, isPending } = authClient.useSession();
  const queryClient = useQueryClient();
  const form = useForm<CreateUserValues>({
    resolver: zodResolver(createUserSchema),
    defaultValues: { name: "", email: "", password: "", role: "user" },
  });

  const users = useQuery({
    queryKey: ["users"],
    enabled: Boolean(session),
    retry: false,
    queryFn: async () => {
      const result = await authClient.admin.listUsers({
        query: { limit: 50, sortBy: "email", sortDirection: "asc" },
      });
      if (result.error) {
        throw new Error(result.error.message ?? "Could not list users.");
      }
      return result.data;
    },
  });

  const createUser = useMutation({
    mutationFn: async (values: CreateUserValues) => {
      const result = await authClient.admin.createUser(values);
      if (result.error) {
        throw new Error(result.error.message ?? "Could not create the user.");
      }
    },
    onSuccess: async () => {
      form.reset();
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  const updateName = useMutation({
    mutationFn: async (user: ManagedUser) => {
      const name = window.prompt("New name", user.name)?.trim();
      if (!name || name === user.name) {
        return;
      }
      const result = await authClient.admin.updateUser({ userId: user.id, data: { name } });
      if (result.error) {
        throw new Error(result.error.message ?? "Could not update the user.");
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  const removeUser = useMutation({
    mutationFn: async (userId: string) => {
      const result = await authClient.admin.removeUser({ userId });
      if (result.error) {
        throw new Error(result.error.message ?? "Could not delete the user.");
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  if (isPending) {
    return <p className="text-sm text-zinc-400">Checking your session…</p>;
  }
  if (!session) {
    return <Navigate to="/login" replace />;
  }

  const rows = (users.data?.users ?? []) as ManagedUser[];
  const actionError = createUser.error ?? updateName.error ?? removeUser.error;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
        <p className="mt-2 text-sm text-zinc-400">
          Listing, creating, updating, and deleting users is limited to admins. Your role is{" "}
          {session.user.role ?? "user"}.
        </p>
      </div>

      {users.isError ? <p className="text-sm text-red-400">{users.error.message}</p> : null}
      {actionError ? <p className="text-sm text-red-400">{actionError.message}</p> : null}

      <form
        onSubmit={form.handleSubmit(async (values) => {
          await createUser.mutateAsync(values);
        })}
        className="grid gap-3 rounded-lg border border-zinc-800 p-4 sm:grid-cols-2"
        noValidate
      >
        <h2 className="sm:col-span-2 text-sm font-medium">Create user</h2>
        <input className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2" placeholder="Name" {...form.register("name")} />
        <input className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2" placeholder="Email" {...form.register("email")} />
        <input
          type="password"
          className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2"
          placeholder="Password"
          {...form.register("password")}
        />
        <select className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2" {...form.register("role")}>
          <option value="user">user</option>
          <option value="admin">admin</option>
        </select>
        <button type="submit" className="sm:col-span-2 w-fit rounded-md bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-950">
          Create
        </button>
      </form>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-zinc-400">
            <tr>
              <th className="py-2 pr-4 font-medium">Name</th>
              <th className="py-2 pr-4 font-medium">Email</th>
              <th className="py-2 pr-4 font-medium">Role</th>
              <th className="py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((user) => (
              <tr key={user.id} className="border-t border-zinc-800">
                <td className="py-2 pr-4">{user.name}</td>
                <td className="py-2 pr-4">{user.email}</td>
                <td className="py-2 pr-4">{user.role ?? "user"}</td>
                <td className="py-2">
                  <button type="button" className="mr-3 underline" onClick={() => updateName.mutate(user)}>
                    Rename
                  </button>
                  <button type="button" className="underline" onClick={() => removeUser.mutate(user.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.isSuccess && rows.length === 0 ? <p className="mt-3 text-sm text-zinc-400">No users yet.</p> : null}
      </div>
    </div>
  );
}
