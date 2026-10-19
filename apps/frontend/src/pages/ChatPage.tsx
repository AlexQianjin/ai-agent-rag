import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router";

import { authClient, conversationsApiUrl, documentsApiUrl } from "../lib/auth-client";
import { type Citation, useChatStream } from "../lib/chat-store";
import { readEventStream } from "../lib/sse";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

type ConversationSummary = {
  id: string;
  title: string;
  updated_at: string;
};

type DocumentSummary = {
  id: string;
  filename: string;
  status: string;
  index_status: string | null;
  index_error: string | null;
  error_message: string | null;
};

type Message = {
  id: string;
  role: string;
  content: string;
  citations: Citation[];
};

type ConversationDetail = {
  id: string;
  title: string;
  messages: Message[];
  documents: DocumentSummary[];
};

export function ChatPage() {
  const { data: session, isPending } = authClient.useSession();
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const stream = useChatStream();
  const [draft, setDraft] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const conversations = useQuery({
    queryKey: ["conversations"],
    enabled: Boolean(session),
    retry: false,
    queryFn: async () => {
      const response = await fetch(conversationsApiUrl(), { credentials: "include" });
      if (!response.ok) {
        throw new Error("Could not load conversations.");
      }
      const body = (await response.json()) as { conversations: ConversationSummary[] };
      return body.conversations;
    },
  });

  const conversation = useQuery({
    queryKey: ["conversation", conversationId],
    enabled: Boolean(session && conversationId),
    retry: false,
    refetchInterval: (query) => {
      const documents = query.state.data?.documents ?? [];
      return documents.some((item) => isInProgress(item.status, item.index_status)) ? 2000 : false;
    },
    queryFn: async () => {
      const response = await fetch(conversationsApiUrl(`/${conversationId}`), { credentials: "include" });
      if (response.status === 404) {
        throw new Error("That conversation is gone.");
      }
      if (!response.ok) {
        throw new Error("Could not load the conversation.");
      }
      return (await response.json()) as ConversationDetail;
    },
  });

  const create = useMutation({
    mutationFn: async () => {
      const response = await fetch(conversationsApiUrl(), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!response.ok) {
        throw new Error("Could not start a conversation.");
      }
      return (await response.json()) as ConversationSummary;
    },
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
      navigate(`/chat/${created.id}`);
    },
  });

  const remove = useMutation({
    mutationFn: async (id: string) => {
      const response = await fetch(conversationsApiUrl(`/${id}`), {
        method: "DELETE",
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error("Could not delete that conversation.");
      }
    },
    onSuccess: async () => {
      setConfirming(false);
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
      navigate("/chat");
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [conversation.data?.messages, stream.draft, stream.status, stream.sources]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  if (isPending) {
    return <p className="p-6 text-sm text-zinc-400">Checking your session…</p>;
  }
  if (!session) {
    return <Navigate to="/login" replace />;
  }

  const messages = conversation.data?.messages ?? [];
  const documents = conversation.data?.documents ?? [];
  const streamingHere = stream.streaming && stream.conversationId === conversationId;

  async function sendMessage() {
    const content = draft.trim();
    if (!conversationId || !content || stream.streaming) {
      return;
    }
    setDraft("");
    stream.begin(conversationId);
    const abort = new AbortController();
    abortRef.current = abort;
    try {
      const response = await fetch(conversationsApiUrl(`/${conversationId}/messages`), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ content }),
        signal: abort.signal,
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "Could not send the message.");
      }
      await queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] });
      await readEventStream(response, (event, data) => {
        if (event === "token") {
          stream.append(String(data.delta ?? ""));
          return;
        }
        if (event === "retrieved") {
          stream.setSources((data.sources as Citation[]) ?? []);
          stream.setStatus(String(data.status ?? "Found passages"));
          return;
        }
        if (event === "error") {
          stream.fail(String(data.message ?? "The assistant is unavailable."));
          return;
        }
        if (typeof data.status === "string") {
          stream.setStatus(data.status);
        }
      });
      await queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] });
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
      if (useChatStream.getState().error === null) {
        stream.finish();
      }
    } catch (error) {
      if (abort.signal.aborted) {
        stream.finish();
        return;
      }
      stream.fail(error instanceof Error ? error.message : "Could not send the message.");
    }
  }

  async function uploadFile(file: File) {
    if (!conversationId) {
      return;
    }
    setUploadError(null);
    if (file.size > MAX_UPLOAD_BYTES) {
      setUploadError("File is larger than 20 MB.");
      return;
    }
    if (!/\.(pdf|docx|txt)$/i.test(file.name)) {
      setUploadError("Use a PDF, DOCX, or TXT file.");
      return;
    }
    const body = new FormData();
    body.set("file", file);
    body.set("conversation_id", conversationId);
    const response = await fetch(documentsApiUrl(), { method: "POST", body, credentials: "include" });
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
      setUploadError(payload?.detail ?? "Upload failed.");
      return;
    }
    await queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] });
  }

  return (
    <div className="grid h-full min-h-0 grid-cols-1 md:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="flex max-h-64 min-h-0 flex-col border-b border-zinc-800 md:max-h-none md:border-r md:border-b-0">
        <div className="flex items-center justify-between px-3 py-3">
          <h1 className="text-sm font-medium">Conversations</h1>
          <button
            type="button"
            className="rounded-md bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-950"
            onClick={() => create.mutate()}
          >
            New conversation
          </button>
        </div>
        {create.error ? <p className="px-3 text-xs text-red-400">{create.error.message}</p> : null}
        <ul className="min-h-0 flex-1 overflow-y-auto">
          {(conversations.data ?? []).map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className={`block w-full truncate px-3 py-2 text-left text-sm ${
                  item.id === conversationId ? "bg-zinc-800 text-zinc-100" : "text-zinc-300"
                }`}
                onClick={() => navigate(`/chat/${item.id}`)}
              >
                {item.title}
              </button>
            </li>
          ))}
        </ul>
        {conversations.isSuccess && conversations.data.length === 0 ? (
          <p className="px-3 pb-3 text-xs text-zinc-500">No conversations yet.</p>
        ) : null}
      </aside>

      <section className="flex min-h-0 flex-col">
        {conversationId ? (
          <>
            <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
              <h2 className="truncate text-sm font-medium">{conversation.data?.title ?? "Conversation"}</h2>
              <button
                type="button"
                className="text-sm text-zinc-300 underline"
                onClick={() => setConfirming(true)}
              >
                Delete conversation
              </button>
            </div>
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
              {conversation.isError ? <p className="text-sm text-red-400">{conversation.error.message}</p> : null}
              {messages.map((message) => (
                <article key={message.id} className="max-w-3xl">
                  <p className="text-xs text-zinc-500">{message.role === "assistant" ? "Assistant" : "You"}</p>
                  <p className="mt-1 whitespace-pre-wrap text-sm">{message.content}</p>
                  {message.role === "assistant" ? <CitationList citations={message.citations} /> : null}
                </article>
              ))}
              {streamingHere ? (
                <article className="max-w-3xl">
                  <p className="text-xs text-zinc-500">Assistant</p>
                  {stream.status ? <p className="mt-1 text-sm text-zinc-400">{stream.status}</p> : null}
                  {stream.draft ? <p className="mt-1 whitespace-pre-wrap text-sm">{stream.draft}</p> : null}
                  <CitationList citations={stream.sources} />
                </article>
              ) : null}
              {stream.error && stream.conversationId === conversationId ? (
                <p className="text-sm text-red-400">{stream.error}</p>
              ) : null}
              <div ref={bottomRef} />
            </div>
            {documents.length > 0 ? (
              <ul className="space-y-1 border-t border-zinc-800 px-4 py-2 text-xs text-zinc-400">
                {documents.map((document) => (
                  <li key={document.id}>
                    {document.filename} · {document.status}
                    {document.index_status ? ` · ${document.index_status}` : ""}
                    {document.index_error ? ` · ${document.index_error}` : ""}
                    {document.error_message ? ` · ${document.error_message}` : ""}
                  </li>
                ))}
              </ul>
            ) : null}
            <form
              className="flex flex-col gap-2 border-t border-zinc-800 p-4"
              onSubmit={(event) => {
                event.preventDefault();
                void sendMessage();
              }}
            >
              {uploadError ? <p className="text-sm text-red-400">{uploadError}</p> : null}
              <div className="flex items-end gap-2">
                <label className="flex-1 text-sm">
                  <span className="sr-only">Message</span>
                  <textarea
                    aria-label="Message"
                    value={draft}
                    rows={2}
                    className="w-full resize-none rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2"
                    placeholder="Ask about your documents"
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        void sendMessage();
                      }
                    }}
                  />
                </label>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf,.docx,.txt,application/pdf,text/plain"
                  className="hidden"
                  aria-label="Upload file"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (file) {
                      void uploadFile(file);
                    }
                  }}
                />
                <button
                  type="button"
                  className="rounded-md border border-zinc-700 px-3 py-2 text-sm"
                  onClick={() => fileRef.current?.click()}
                >
                  Upload file
                </button>
                <button
                  type="submit"
                  className="rounded-md bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-950 disabled:opacity-50"
                  disabled={stream.streaming || draft.trim() === ""}
                >
                  Send
                </button>
              </div>
            </form>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center p-6 text-sm text-zinc-400">
            Choose a conversation or start a new one.
          </div>
        )}
      </section>

      {confirming && conversationId ? (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/60 p-4" role="presentation">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-conversation-title"
            className="w-full max-w-sm rounded-lg border border-zinc-700 bg-zinc-900 p-4"
          >
            <h2 id="delete-conversation-title" className="text-base font-medium">
              Delete this conversation?
            </h2>
            <p className="mt-2 text-sm text-zinc-400">
              Messages in this conversation will be removed. Uploaded documents stay in your library.
            </p>
            {remove.error ? <p className="mt-2 text-sm text-red-400">{remove.error.message}</p> : null}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-md border border-zinc-700 px-3 py-2 text-sm"
                onClick={() => setConfirming(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-md bg-red-500 px-3 py-2 text-sm font-medium text-white"
                onClick={() => remove.mutate(conversationId)}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return null;
  }
  return (
    <ul className="mt-2 space-y-2">
      {citations.map((citation) => (
        <li
          key={`${citation.document_id}-${citation.chunk_index}`}
          className="rounded-md border border-zinc-800 bg-zinc-900/60 p-2 text-xs text-zinc-300"
        >
          <p className="text-zinc-400">
            {citation.document_name} · chunk {citation.chunk_index}
            {citation.headings.length > 0 ? ` · ${citation.headings.join(" / ")}` : ""}
          </p>
          <p className="mt-1 whitespace-pre-wrap">{citation.text}</p>
        </li>
      ))}
    </ul>
  );
}

function isInProgress(status: string, indexStatus: string | null): boolean {
  return status === "pending" || status === "processing" || indexStatus === "pending" || indexStatus === "indexing";
}
