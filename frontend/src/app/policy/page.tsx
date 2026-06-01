"use client";

import { useState } from "react";

import { ConfidenceBadge } from "@/components/StatusBadge";
import { EmptyState, ErrorBanner } from "@/components/States";
import { Spinner } from "@/components/Spinner";
import { api, ApiError } from "@/lib/api";
import type { PolicySearchResponse } from "@/types";

export default function PolicySearchPage() {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<PolicySearchResponse | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setResponse(await api.policySearch(query.trim(), topK));
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setError(
          "Policy search is unavailable — the backend has no OPENAI_API_KEY configured for embeddings.",
        );
      } else {
        setError(err instanceof ApiError ? err.message : "Search failed.");
      }
      setResponse(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Policy search</h1>
        <p className="text-sm text-slate-500">
          Semantic search over the expense policy documents. This is retrieval
          only — it returns the most relevant policy passages, not a generated
          answer.
        </p>
      </div>

      <form
        onSubmit={handleSearch}
        className="space-y-3 rounded-lg border border-slate-200 bg-white p-4"
      >
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">
            Question
          </label>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. Can directors fly business class?"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          />
        </div>
        <div className="flex items-end gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">
              Results
            </label>
            <select
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
            >
              {[3, 5, 10, 15, 20].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {loading && (
              <Spinner size="sm" className="border-white/40 border-t-white" />
            )}
            Search
          </button>
        </div>
      </form>

      {error && <ErrorBanner message={error} />}

      {response && !loading && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <span>
              {response.results.length} result
              {response.results.length === 1 ? "" : "s"} for “{response.query}”
            </span>
            <span className="text-slate-300">·</span>
            <span className="flex items-center gap-1">
              Overall confidence <ConfidenceBadge value={response.confidence} />
            </span>
          </div>

          {response.results.length === 0 ? (
            <EmptyState
              title="No matching policy passages"
              description="Try rephrasing the question or broadening the terms."
            />
          ) : (
            <ul className="space-y-3">
              {response.results.map((r, i) => (
                <li
                  key={i}
                  className="rounded-lg border border-slate-200 bg-white p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-medium text-slate-800">
                      {r.document_id}
                      {r.page_number != null && (
                        <span className="text-slate-400"> · p.{r.page_number}</span>
                      )}
                      {r.section && (
                        <span className="text-slate-400"> · §{r.section}</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-400">
                        similarity {r.similarity.toFixed(2)}
                      </span>
                      <ConfidenceBadge value={r.confidence} />
                    </div>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">
                    {r.chunk_text}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
