import { create } from "zustand";

export type Citation = {
  document_id: string;
  document_name: string;
  chunk_index: number;
  text: string;
  headings: string[];
  score: number;
};

type ChatStreamState = {
  conversationId: string | null;
  status: string | null;
  draft: string;
  sources: Citation[];
  streaming: boolean;
  error: string | null;
  begin: (conversationId: string) => void;
  setStatus: (status: string | null) => void;
  append: (delta: string) => void;
  setSources: (sources: Citation[]) => void;
  fail: (message: string) => void;
  finish: () => void;
};

export const useChatStream = create<ChatStreamState>((set) => ({
  conversationId: null,
  status: null,
  draft: "",
  sources: [],
  streaming: false,
  error: null,
  begin: (conversationId) =>
    set({
      conversationId,
      status: "Thinking…",
      draft: "",
      sources: [],
      streaming: true,
      error: null,
    }),
  setStatus: (status) => set({ status }),
  append: (delta) => set((state) => ({ draft: state.draft + delta })),
  setSources: (sources) => set({ sources }),
  fail: (message) => set({ error: message, streaming: false, status: null }),
  finish: () => set({ streaming: false, status: null, draft: "", sources: [] }),
}));
