"use client";

import { useState } from "react";

import { OverrideModal } from "@/components/OverrideModal";
import { StatusBadge } from "@/components/StatusBadge";
import {
  formatConfidence,
  formatDate,
  formatMoney,
  humanize,
} from "@/lib/format";
import { statusStyle } from "@/lib/status";
import type { ReceiptWithVerdict, Verdict } from "@/types";

interface ReceiptCardProps {
  receipt: ReceiptWithVerdict;
  /** Called when a verdict is overridden, so the parent can update its state. */
  onVerdictUpdated: (receiptId: string, verdict: Verdict) => void;
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium text-slate-800">{value}</dd>
    </div>
  );
}

export function ReceiptCard({ receipt, onVerdictUpdated }: ReceiptCardProps) {
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [showRawText, setShowRawText] = useState(false);
  const verdict = receipt.verdict;

  // The card accent reflects the effective decision (override wins), or neutral
  // when the receipt has not been reviewed yet.
  const accent = verdict
    ? statusStyle(verdict.effective_verdict).accentBorder
    : "border-l-slate-200";

  const isOverridden =
    verdict && verdict.effective_verdict !== verdict.verdict;

  return (
    <div className={`rounded-lg border border-slate-200 border-l-4 bg-white shadow-sm ${accent}`}>
      <div className="flex flex-wrap items-start justify-between gap-3 p-4">
        <div>
          <h3 className="text-base font-semibold text-slate-900">
            {receipt.merchant ?? receipt.original_filename}
          </h3>
          <p className="text-xs text-slate-400">{receipt.original_filename}</p>
        </div>
        {verdict ? (
          <div className="flex items-center gap-2">
            {isOverridden && (
              <span className="text-xs text-slate-400 line-through">
                {humanize(verdict.verdict)}
              </span>
            )}
            <StatusBadge value={verdict.effective_verdict} />
          </div>
        ) : (
          <span className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-medium text-slate-500">
            Not reviewed
          </span>
        )}
      </div>

      {/* Receipt fields */}
      <dl className="grid grid-cols-2 gap-4 border-t border-slate-100 px-4 py-3 sm:grid-cols-4">
        <Field label="Date" value={formatDate(receipt.transaction_date)} />
        <Field
          label="Amount"
          value={formatMoney(receipt.amount, receipt.currency)}
        />
        <Field label="Currency" value={receipt.currency || "—"} />
        <Field
          label="Category"
          value={receipt.category ? humanize(receipt.category) : "—"}
        />
      </dl>

      {/* Raw extracted text preview */}
      {receipt.raw_extracted_text && (
        <div className="border-t border-slate-100 px-4 py-3">
          <button
            onClick={() => setShowRawText((v) => !v)}
            className="text-xs font-medium text-slate-500 hover:text-slate-800"
          >
            {showRawText ? "Hide" : "Show"} extracted text
          </button>
          {showRawText ? (
            <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-slate-50 p-3 text-xs text-slate-600">
              {receipt.raw_extracted_text}
            </pre>
          ) : (
            <p className="mt-1 line-clamp-2 text-xs text-slate-400">
              {receipt.raw_extracted_text.slice(0, 160)}
              {receipt.raw_extracted_text.length > 160 ? "…" : ""}
            </p>
          )}
        </div>
      )}

      {/* Verdict detail */}
      {verdict && (
        <div className="space-y-4 border-t border-slate-100 px-4 py-4">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="text-slate-500">
              AI verdict:{" "}
              <span className="font-medium text-slate-800">
                {humanize(verdict.verdict)}
              </span>
            </span>
            <span className="text-slate-300">·</span>
            <span className="text-slate-500">
              Effective:{" "}
              <span className="font-medium text-slate-800">
                {humanize(verdict.effective_verdict)}
              </span>
            </span>
            <span className="text-slate-300">·</span>
            <span className="text-slate-500">
              Confidence:{" "}
              <span className="font-medium text-slate-800">
                {formatConfidence(verdict.confidence)}
              </span>
            </span>
          </div>

          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Reasoning
            </h4>
            <p className="mt-1 text-sm text-slate-700">{verdict.reasoning}</p>
          </div>

          {verdict.policy_citations.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Policy citations
              </h4>
              <ul className="mt-1 space-y-1">
                {verdict.policy_citations.map((c, i) => (
                  <li key={i} className="text-sm text-slate-700">
                    <span className="font-medium">{c.document_id}</span>
                    {c.page_number != null && ` · p.${c.page_number}`}
                    {c.section && ` · §${c.section}`}
                    {c.reason && (
                      <span className="text-slate-500"> — {c.reason}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {verdict.quoted_policy_clauses.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Quoted policy clauses
              </h4>
              <ul className="mt-1 space-y-2">
                {verdict.quoted_policy_clauses.map((q, i) => (
                  <li
                    key={i}
                    className="border-l-2 border-slate-200 pl-3 text-sm italic text-slate-600"
                  >
                    “{q.quote}”
                    <span className="ml-1 not-italic text-xs text-slate-400">
                      — {q.document_id}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Override history */}
          {verdict.overrides.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Override history
              </h4>
              <ul className="mt-1 space-y-2">
                {verdict.overrides.map((o) => (
                  <li
                    key={o.id}
                    className="rounded-md border border-slate-100 bg-slate-50 px-3 py-2 text-sm"
                  >
                    <div className="flex items-center justify-between">
                      <StatusBadge value={o.override_verdict} />
                      <span className="text-xs text-slate-400">
                        {formatDate(o.created_at)}
                      </span>
                    </div>
                    <p className="mt-1 text-slate-700">
                      <span className="font-medium">{o.reviewer_name}</span>
                      {o.comment && <span className="text-slate-500"> — {o.comment}</span>}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex justify-end">
            <button
              onClick={() => setOverrideOpen(true)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Override
            </button>
          </div>
        </div>
      )}

      {verdict && (
        <OverrideModal
          open={overrideOpen}
          onClose={() => setOverrideOpen(false)}
          verdict={verdict}
          onOverridden={(updated) => onVerdictUpdated(receipt.id, updated)}
        />
      )}
    </div>
  );
}
