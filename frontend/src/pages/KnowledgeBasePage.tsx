import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth/context";
import { Alert } from "../components/forms";
import { useApiQuery } from "../hooks/useApiQuery";
import { ApiError } from "../lib/api";
import { formatDateTime } from "../lib/inbox";
import { deleteDocument, reprocessDocument, searchKnowledge, uploadDocument } from "../lib/knowledge";
import type { KnowledgeDocument, KnowledgeSearchHit, PageResponse } from "../types/api";

const PAGE_SIZE = 20;
const MAX_BYTES = 10 * 1024 * 1024;
const ALLOWED = ["pdf", "docx", "txt", "csv"];

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
  deleted: "Deleted",
};

export default function KnowledgeBasePage() {
  const { organization } = useAuth();
  const organizationId = organization?.id;
  const canManage = organization?.role === "owner" || organization?.role === "admin";
  const [offset, setOffset] = useState(0);
  const list = useApiQuery<PageResponse<KnowledgeDocument>>(
    `/api/knowledge/documents?limit=${PAGE_SIZE}&offset=${offset}`,
    organizationId,
  );
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selected, setSelected] = useState<KnowledgeDocument | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<KnowledgeSearchHit[] | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  const waiting = list.data?.items.some((item) => item.status === "pending" || item.status === "processing");
  const reload = list.reload;
  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(() => reload(), 2000);
    return () => window.clearInterval(timer);
  }, [waiting, reload]);

  function onFile(next: File | null) {
    setUploadError(null);
    if (!next) {
      setFile(null);
      setFileError(null);
      return;
    }
    const extension = next.name.split(".").pop()?.toLowerCase() ?? "";
    if (!ALLOWED.includes(extension)) {
      setFile(null);
      setFileError("Upload a PDF, DOCX, TXT, or CSV file.");
      return;
    }
    if (next.size > MAX_BYTES) {
      setFile(null);
      setFileError("This file is too large. The limit is 10 MB.");
      return;
    }
    if (next.size === 0) {
      setFile(null);
      setFileError("This file is empty.");
      return;
    }
    setFileError(null);
    setFile(next);
  }

  async function onUpload(event: FormEvent) {
    event.preventDefault();
    if (!organizationId || !file) return;
    setUploading(true);
    setUploadError(null);
    try {
      await uploadDocument(organizationId, file);
      setFile(null);
      list.reload();
    } catch (caught) {
      setUploadError(caught instanceof ApiError ? caught.message : "The upload could not be completed.");
    } finally {
      setUploading(false);
    }
  }

  async function onReprocess(documentId: string) {
    if (!organizationId) return;
    setBusyId(documentId);
    setActionError(null);
    try {
      await reprocessDocument(organizationId, documentId);
      list.reload();
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "Could not reprocess this document.");
    } finally {
      setBusyId(null);
    }
  }

  async function onDelete(documentId: string) {
    if (!organizationId) return;
    setBusyId(documentId);
    setActionError(null);
    try {
      await deleteDocument(organizationId, documentId);
      if (selected?.id === documentId) setSelected(null);
      list.reload();
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "Could not delete this document.");
    } finally {
      setBusyId(null);
    }
  }

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    if (!organizationId || !query.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      const result = await searchKnowledge(organizationId, query.trim());
      setHits(result.items);
    } catch (caught) {
      setHits(null);
      setSearchError(caught instanceof ApiError ? caught.message : "Search could not be completed.");
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Knowledge Base</h1>
        <p className="mt-1 text-sm text-slate-600">
          Upload business documents that AI can use when answering customers.
        </p>
      </div>

      {canManage && (
        <form onSubmit={(event) => void onUpload(event)} className="rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="font-semibold">Upload document</h2>
          <label className="mt-3 block text-sm font-medium text-slate-700" htmlFor="knowledge-file">
            PDF, DOCX, TXT, or CSV
          </label>
          <input
            id="knowledge-file"
            type="file"
            accept=".pdf,.docx,.txt,.csv,application/pdf,text/plain,text/csv"
            className="mt-1 block w-full text-sm"
            onChange={(event) => onFile(event.target.files?.[0] ?? null)}
          />
          {file && (
            <p className="mt-2 text-sm text-slate-600">
              {file.name} · {Math.max(1, Math.round(file.size / 1024))} KB
            </p>
          )}
          {fileError && (
            <div className="mt-3">
              <Alert tone="error">{fileError}</Alert>
            </div>
          )}
          {uploadError && (
            <div className="mt-3">
              <Alert tone="error">{uploadError}</Alert>
            </div>
          )}
          <button
            type="submit"
            disabled={!file || uploading}
            className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {uploading ? "Uploading…" : "Upload document"}
          </button>
        </form>
      )}

      <section className="rounded-xl border border-slate-200 bg-white">
        {list.loading && !list.data && <p className="p-5 text-sm text-slate-500">Loading…</p>}
        {list.error && (
          <div className="p-5">
            <Alert tone="error">{list.error}</Alert>
          </div>
        )}
        {actionError && (
          <div className="px-5 pt-5">
            <Alert tone="error">{actionError}</Alert>
          </div>
        )}
        {list.data && list.data.items.length === 0 && (
          <p className="p-5 text-sm text-slate-600">No documents yet. Upload a PDF, DOCX, TXT, or CSV.</p>
        )}
        {list.data && list.data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Chunks</th>
                  <th className="px-4 py-3 font-medium">Created</th>
                  <th className="px-4 py-3 font-medium">Updated</th>
                  <th className="px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((document) => (
                  <tr key={document.id} className="border-b border-slate-100 align-top">
                    <td className="px-4 py-3 font-medium">{document.name}</td>
                    <td className="px-4 py-3 uppercase">{document.file_type}</td>
                    <td className="px-4 py-3">
                      <span>{STATUS_LABEL[document.status] ?? document.status}</span>
                      {document.status === "failed" && document.error_message && (
                        <p className="mt-1 text-xs text-red-700">{document.error_message}</p>
                      )}
                    </td>
                    <td className="px-4 py-3">{document.chunk_count}</td>
                    <td className="px-4 py-3">{formatDateTime(document.created_at)}</td>
                    <td className="px-4 py-3">{formatDateTime(document.updated_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-2">
                        <button type="button" className="text-brand-600 hover:underline" onClick={() => setSelected(document)}>
                          View
                        </button>
                        {canManage && (
                          <button
                            type="button"
                            className="text-slate-700 hover:underline disabled:opacity-60"
                            disabled={busyId === document.id || document.status === "processing"}
                            onClick={() => void onReprocess(document.id)}
                          >
                            Reprocess
                          </button>
                        )}
                        {canManage && (
                          <button
                            type="button"
                            className="text-red-700 hover:underline disabled:opacity-60"
                            disabled={busyId === document.id}
                            onClick={() => void onDelete(document.id)}
                          >
                            {busyId === document.id ? "Working…" : "Delete"}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {(offset > 0 || list.data?.has_more) && (
          <div className="flex justify-between px-4 py-3 text-sm">
            <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} className="text-brand-600 disabled:text-slate-300">
              Newer
            </button>
            <button type="button" disabled={!list.data?.has_more} onClick={() => setOffset(offset + PAGE_SIZE)} className="text-brand-600 disabled:text-slate-300">
              Older
            </button>
          </div>
        )}
      </section>

      {selected && (
        <section className="rounded-xl border border-slate-200 bg-white p-5 text-sm">
          <h2 className="font-semibold">{selected.name}</h2>
          <dl className="mt-3 grid grid-cols-[8rem_1fr] gap-y-1">
            <dt className="text-slate-500">File</dt>
            <dd>{selected.original_filename}</dd>
            <dt className="text-slate-500">Status</dt>
            <dd>{STATUS_LABEL[selected.status] ?? selected.status}</dd>
            <dt className="text-slate-500">Chunks</dt>
            <dd>{selected.chunk_count}</dd>
            <dt className="text-slate-500">Processed</dt>
            <dd>{formatDateTime(selected.processed_at)}</dd>
          </dl>
          {selected.error_message && <p className="mt-3 text-red-700">{selected.error_message}</p>}
        </section>
      )}

      <form onSubmit={(event) => void onSearch(event)} className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="font-semibold">Search knowledge</h2>
        <label className="mt-3 block text-sm font-medium text-slate-700" htmlFor="knowledge-query">
          Question
        </label>
        <div className="mt-1 flex gap-2">
          <input
            id="knowledge-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="What is the return policy?"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={searching || !query.trim()}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {searching ? "Searching…" : "Search"}
          </button>
        </div>
        {searchError && (
          <div className="mt-3">
            <Alert tone="error">{searchError}</Alert>
          </div>
        )}
        {hits && hits.length === 0 && <p className="mt-3 text-sm text-slate-600">No relevant business knowledge found.</p>}
        {hits && hits.length > 0 && (
          <ul className="mt-4 space-y-3">
            {hits.map((hit) => (
              <li key={hit.chunk_id} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <p className="font-medium">
                  {hit.document_name}
                  {hit.page ? ` — page ${hit.page}` : ""}
                  <span className="ml-2 font-normal text-slate-500">relevance {hit.relevance.toFixed(2)}</span>
                </p>
                <p className="mt-1 whitespace-pre-wrap text-slate-700">{hit.content}</p>
              </li>
            ))}
          </ul>
        )}
      </form>
    </div>
  );
}
