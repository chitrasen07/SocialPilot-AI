import { api } from "./api";
import type { KnowledgeDocument, KnowledgeSearchHit, PageResponse } from "../types/api";

export function listDocuments(organizationId: string, limit = 20, offset = 0) {
  return api<PageResponse<KnowledgeDocument>>(
    `/api/knowledge/documents?limit=${limit}&offset=${offset}`,
    { organizationId },
  );
}

export function uploadDocument(organizationId: string, file: File, name?: string) {
  const form = new FormData();
  form.set("file", file);
  if (name) form.set("name", name);
  return api<KnowledgeDocument>("/api/knowledge/documents", {
    method: "POST",
    form,
    organizationId,
  });
}

export function getDocument(organizationId: string, documentId: string) {
  return api<KnowledgeDocument>(`/api/knowledge/documents/${documentId}`, { organizationId });
}

export function deleteDocument(organizationId: string, documentId: string) {
  return api<void>(`/api/knowledge/documents/${documentId}`, { method: "DELETE", organizationId });
}

export function reprocessDocument(organizationId: string, documentId: string) {
  return api<KnowledgeDocument>(`/api/knowledge/documents/${documentId}/reprocess`, {
    method: "POST",
    organizationId,
  });
}

export function searchKnowledge(organizationId: string, query: string, topK = 5) {
  return api<{ items: KnowledgeSearchHit[] }>("/api/knowledge/search", {
    method: "POST",
    organizationId,
    body: { query, top_k: topK },
  });
}
