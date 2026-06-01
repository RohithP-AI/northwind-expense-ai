"use client";

import { useState } from "react";

import { Modal } from "@/components/Modal";
import { ErrorBanner } from "@/components/States";
import { Spinner } from "@/components/Spinner";
import { api, ApiError } from "@/lib/api";
import { humanize } from "@/lib/format";
import { VERDICT_OPTIONS } from "@/lib/status";
import type { Verdict, VerdictValue } from "@/types";

interface OverrideModalProps {
  open: boolean;
  onClose: () => void;
  verdict: Verdict;
  /** Called with the refreshed verdict after a successful override. */
  onOverridden: (updated: Verdict) => void;
}

export function OverrideModal({
  open,
  onClose,
  verdict,
  onOverridden,
}: OverrideModalProps) {
  const [overrideVerdict, setOverrideVerdict] = useState<VerdictValue>(
    verdict.effective_verdict,
  );
  const [reviewerName, setReviewerName] = useState("");
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!reviewerName.trim()) {
      setError("Reviewer name is required.");
      return;
    }
    setSubmitting(true);
    try {
      const updated = await api.overrideVerdict(verdict.id, {
        override_verdict: overrideVerdict,
        reviewer_name: reviewerName.trim(),
        comment: comment.trim() || undefined,
      });
      onOverridden(updated);
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to submit override.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Override verdict">
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-slate-500">
          Overrides never change the original AI verdict — they are appended to an
          audit trail, and the latest one becomes the effective decision.
        </p>

        {error && <ErrorBanner message={error} />}

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">
            Override verdict
          </label>
          <select
            value={overrideVerdict}
            onChange={(e) => setOverrideVerdict(e.target.value as VerdictValue)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          >
            {VERDICT_OPTIONS.map((v) => (
              <option key={v} value={v}>
                {humanize(v)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">
            Reviewer name <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={reviewerName}
            onChange={(e) => setReviewerName(e.target.value)}
            placeholder="e.g. Jordan Lee"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">
            Comment
          </label>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={3}
            placeholder="Optional context for this decision"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          />
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {submitting && <Spinner size="sm" className="border-white/40 border-t-white" />}
            Submit override
          </button>
        </div>
      </form>
    </Modal>
  );
}
