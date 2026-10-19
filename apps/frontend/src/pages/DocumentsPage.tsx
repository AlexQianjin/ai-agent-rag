import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate } from "react-router";
import { z } from "zod";

import { authClient, documentsApiUrl } from "../lib/auth-client";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

const uploadSchema = z.object({
  file: z
    .custom<File>((value) => value instanceof File, "Choose a file")
    .refine((file) => file.size > 0, "The file is empty")
    .refine((file) => file.size <= MAX_UPLOAD_BYTES, "File is larger than 20 MB")
    .refine(
      (file) => /\.(pdf|docx|txt|md|markdown)$/i.test(file.name),
      "Use a PDF, DOCX, TXT, or Markdown file",
    ),
});

type UploadValues = z.infer<typeof uploadSchema>;

type DocumentSummary = {
  id: string;
  filename: string;
  mime_type: string;
  status: string;
  error_message: string | null;
  created_at: string;
};

type DocumentDetail = DocumentSummary & {
  markdown: string | null;
};

export function DocumentsPage() {
  const { data: session, isPending } = authClient.useSession();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const form = useForm<UploadValues>({
    resolver: zodResolver(uploadSchema),
  });

  const documents = useQuery({
    queryKey: ["documents"],
    enabled: Boolean(session),
    retry: false,
    refetchInterval: (query) => {
      const rows = query.state.data ?? [];
      return rows.some((item) => item.status === "pending" || item.status === "processing") ? 2000 : false;
    },
    queryFn: async () => {
      const response = await fetch(documentsApiUrl(), { credentials: "include" });
      if (!response.ok) {
        throw new Error("Could not load documents.");
      }
      const body = (await response.json()) as { documents: DocumentSummary[] };
      return body.documents;
    },
  });

  const detail = useQuery({
    queryKey: ["documents", selectedId],
    enabled: Boolean(session && selectedId),
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "processing" ? 2000 : false;
    },
    queryFn: async () => {
      const response = await fetch(documentsApiUrl(`/${selectedId}`), { credentials: "include" });
      if (!response.ok) {
        throw new Error("Could not load that document.");
      }
      return (await response.json()) as DocumentDetail;
    },
  });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.set("file", file);
      const response = await fetch(documentsApiUrl(), {
        method: "POST",
        body,
        credentials: "include",
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "Upload failed.");
      }
      return (await response.json()) as DocumentSummary;
    },
    onSuccess: async (created) => {
      form.reset();
      setSelectedId(created.id);
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  if (isPending) {
    return <p className="text-sm text-zinc-400">Checking your session…</p>;
  }
  if (!session) {
    return <Navigate to="/login" replace />;
  }

  const rows = documents.data ?? [];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
        <p className="mt-2 text-sm text-zinc-400">
          PDF and Word files are converted with Docling. Text and Markdown are stored as they are. Uploads are limited
          to 20 MB.
        </p>
      </div>

      <form
        className="space-y-3 rounded-lg border border-zinc-800 p-4"
        onSubmit={form.handleSubmit(async (values) => {
          await upload.mutateAsync(values.file);
        })}
        noValidate
      >
        <label className="block text-sm">
          File
          <input
            type="file"
            accept=".pdf,.docx,.txt,.md,.markdown,application/pdf,text/plain,text/markdown"
            className="mt-1 block w-full text-sm"
            onChange={(event) => {
              const chosen = event.target.files?.[0];
              if (chosen) {
                form.setValue("file", chosen, { shouldValidate: true });
              }
            }}
          />
        </label>
        {form.formState.errors.file ? <p className="text-sm text-red-400">{form.formState.errors.file.message}</p> : null}
        {upload.error ? <p className="text-sm text-red-400">{upload.error.message}</p> : null}
        <button type="submit" className="rounded-md bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-950">
          Upload
        </button>
      </form>

      {documents.isError ? <p className="text-sm text-red-400">{documents.error.message}</p> : null}

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-zinc-400">
            <tr>
              <th className="py-2 pr-4 font-medium">Name</th>
              <th className="py-2 pr-4 font-medium">Type</th>
              <th className="py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((document) => (
              <tr key={document.id} className="border-t border-zinc-800">
                <td className="py-2 pr-4">
                  <button type="button" className="underline" onClick={() => setSelectedId(document.id)}>
                    {document.filename}
                  </button>
                </td>
                <td className="py-2 pr-4 text-zinc-400">{document.mime_type}</td>
                <td className="py-2">{document.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {documents.isSuccess && rows.length === 0 ? <p className="mt-3 text-sm text-zinc-400">No documents yet.</p> : null}
      </div>

      {selectedId ? (
        <section className="space-y-3">
          <h2 className="text-sm font-medium">Markdown preview</h2>
          {detail.isError ? <p className="text-sm text-red-400">{detail.error.message}</p> : null}
          {detail.data?.error_message ? <p className="text-sm text-red-400">{detail.data.error_message}</p> : null}
          {detail.data?.status === "ready" ? (
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-zinc-800 bg-zinc-900 p-4 text-sm">
              {detail.data.markdown}
            </pre>
          ) : (
            <p className="text-sm text-zinc-400">Status: {detail.data?.status ?? "loading"}</p>
          )}
        </section>
      ) : null}
    </div>
  );
}
