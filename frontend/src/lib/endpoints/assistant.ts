import { request } from "@/lib/apiClient";
import type { AssistantChatRequest, AssistantChatResponse, KnowledgeDocument } from "@/types/api";

export const assistantApi = {
  chat: (body: AssistantChatRequest, signal?: AbortSignal) =>
    request<AssistantChatResponse>("/assistant/chat", { method: "POST", body, signal }),
  listSources: (page = 1) =>
    request<{ items: KnowledgeDocument[]; page: number; page_size: number; total: number; total_pages: number }>(
      "/assistant/sources",
      { query: { page, page_size: 50 } }
    ),
};
