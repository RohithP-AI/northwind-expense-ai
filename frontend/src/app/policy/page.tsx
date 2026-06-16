"use client";

import { useState } from "react";

import { ConfidenceBadge } from "@/components/StatusBadge";
import { ErrorBanner } from "@/components/States";
import { Spinner } from "@/components/Spinner";
import { api, ApiError } from "@/lib/api";
import type { PolicyAnswerResponse } from "@/types";

const EXAMPLES = [
  "What is the meal reimbursement limit?",
  "Can I book business-class travel?",
  "Is manager approval required for hotels above the limit?",
  "Are alcohol expenses reimbursable?",
];

export default function PolicyAssistantPage() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<PolicyAnswerResponse | null>(null);

  async function ask() {
    const trimmed = question.trim();
    if (!trimmed || loading) return; // guard against duplicate submissions
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await api.policyAnswer(trimmed));
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setError(
          "The policy assistant is temporarily unavailable. Please try again later.",
        );
      } else {
        setError(
          err instanceof ApiError
            ? err.message
            : "Something went wrong. Please try again.",
        );
      }
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    ask();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Enter submits; Shift+Enter inserts a newline.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask();
    }
  }

  const canAsk = question.trim().length > 0 && !loading;

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <div>
        <h1 className="text-3xl font-semibold text-slate-900">Policy Assistant</h1>
        <p className="mt-2 text-base text-slate-600">
          Ask a question about the company travel &amp; expense policy and get a
          direct answer.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
      >
        <label
          htmlFor="policy-question"
          className="block text-base font-medium text-slate-700"
        >
          Your question
        </label>
        <textarea
          id="policy-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
          placeholder="e.g. What is the meal reimbursement limit?"
          className="w-full resize-y rounded-lg border border-slate-300 px-4 py-3 text-lg leading-relaxed text-slate-900 placeholder:text-slate-400 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200"
        />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-sm text-slate-400">
            Press Enter to ask · Shift + Enter for a new line
          </span>
          <button
            type="submit"
            disabled={!canAsk}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-6 py-3 text-base font-semibold text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading && (
              <Spinner size="sm" className="border-white/40 border-t-white" />
            )}
            {loading ? "Thinking…" : "Ask"}
          </button>
        </div>
      </form>

      {!answer && !loading && !error && (
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => setQuestion(ex)}
              className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50"
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-6 text-base text-slate-600"
        >
          <Spinner size="md" />
          <span>Reviewing the company policies…</span>
        </div>
      )}

      {error && !loading && <ErrorBanner message={error} />}

      {answer && !loading && (
        <article className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-500">
            <span>Confidence:</span>
            <ConfidenceBadge value={answer.confidence} />
          </div>
          <div className="space-y-4 whitespace-pre-wrap text-[17px] leading-7 text-slate-800">
            {answer.answer}
          </div>
        </article>
      )}
    </div>
  );
}
