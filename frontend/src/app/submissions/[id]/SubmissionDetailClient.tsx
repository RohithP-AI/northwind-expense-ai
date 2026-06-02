"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ReceiptCard } from "@/components/ReceiptCard";
import { LoadingState, Spinner } from "@/components/Spinner";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState, ErrorBanner, ErrorState } from "@/components/States";
import { api, ApiError } from "@/lib/api";
import { formatDate, formatDateRange } from "@/lib/format";
import type { SubmissionDetail, Verdict } from "@/types";

const ACCEPT = ".pdf,.txt,.jpg,.jpeg,.png";

export default function SubmissionDetailClient() {
  const params = useParams<{ id: string }>();
  const pathname = usePathname();
  // Under static export, /submissions/<uuid> is served by the pre-rendered "_"
  // placeholder shell, so useParams() can return the build-time "_" instead of
  // the real id. The browser URL always has the real value, so derive the id
  // from the path; fall back to the param only if the path can't be read.
  const id = useMemo(() => {
    const path =
      typeof window !== "undefined" ? window.location.pathname : pathname ?? "";
    const segments = path.split("/").filter(Boolean);
    const fromPath = segments[0] === "submissions" ? segments[1] : undefined;
    if (fromPath && fromPath !== "_") return decodeURIComponent(fromPath);
    return params.id;
  }, [pathname, params.id]);

  const [submission, setSubmission] = useState<SubmissionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadWarnings, setUploadWarnings] = useState<string[]>([]);

  const [reviewing, setReviewing] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewNotice, setReviewNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSubmission(await api.getSubmission(id));
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to load submission.",
      );
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleUpload() {
    if (selectedFiles.length === 0) return;
    setUploading(true);
    setUploadError(null);
    setUploadWarnings([]);
    try {
      const res = await api.uploadReceipts(id, selectedFiles);
      setUploadWarnings(res.warnings ?? []);
      setSelectedFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await load(); // refresh receipts list
    } catch (err) {
      setUploadError(
        err instanceof ApiError ? err.message : "Upload failed.",
      );
    } finally {
      setUploading(false);
    }
  }

  async function handleReview() {
    setReviewing(true);
    setReviewError(null);
    setReviewNotice(null);
    try {
      const res = await api.reviewSubmission(id);
      setReviewNotice(
        res.reviewed === 0
          ? "No new receipts to review — all receipts already have a verdict."
          : `Reviewed ${res.reviewed} receipt${res.reviewed === 1 ? "" : "s"}.`,
      );
      await load(); // refresh verdicts
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setReviewError(
          "AI review is unavailable — the backend has no ANTHROPIC_API_KEY configured.",
        );
      } else {
        setReviewError(
          err instanceof ApiError ? err.message : "Review failed.",
        );
      }
    } finally {
      setReviewing(false);
    }
  }

  function handleVerdictUpdated(receiptId: string, verdict: Verdict) {
    setSubmission((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        receipts: prev.receipts.map((r) =>
          r.id === receiptId ? { ...r, verdict } : r,
        ),
      };
    });
  }

  if (loading) return <LoadingState label="Loading submission…" />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!submission) return <ErrorState message="Submission not found." />;

  const { employee, receipts } = submission;
  const hasUnreviewed = receipts.some((r) => r.verdict === null);

  return (
    <div className="space-y-6">
      <div>
        <Link href="/" className="text-sm text-slate-500 hover:text-slate-800">
          ← Back to submissions
        </Link>
      </div>

      {/* Trip + employee context */}
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">
              {submission.trip_purpose}
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              {formatDateRange(
                submission.trip_start_date,
                submission.trip_end_date,
              )}{" "}
              · Created {formatDate(submission.created_at)}
            </p>
          </div>
          <StatusBadge value={submission.status} />
        </div>

        <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-slate-100 pt-4 sm:grid-cols-4">
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-400">
              Employee
            </dt>
            <dd className="mt-0.5 text-sm font-medium text-slate-800">
              {employee?.name ?? submission.employee_id}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-400">
              Title
            </dt>
            <dd className="mt-0.5 text-sm font-medium text-slate-800">
              {employee?.title ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-400">
              Department
            </dt>
            <dd className="mt-0.5 text-sm font-medium text-slate-800">
              {employee?.department ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-400">
              Home base
            </dt>
            <dd className="mt-0.5 text-sm font-medium text-slate-800">
              {employee?.home_base ?? "—"}
            </dd>
          </div>
        </dl>
      </div>

      {/* Upload area */}
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <h2 className="text-base font-semibold text-slate-900">Receipts</h2>
        <p className="text-sm text-slate-500">
          Upload one or more receipts (PDF, TXT, JPG, PNG). Fields are extracted
          automatically.
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPT}
            onChange={(e) =>
              setSelectedFiles(e.target.files ? Array.from(e.target.files) : [])
            }
            className="block text-sm text-slate-600 file:mr-3 file:rounded-md file:border file:border-slate-300 file:bg-slate-50 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-slate-700 hover:file:bg-slate-100"
          />
          <button
            onClick={handleUpload}
            disabled={uploading || selectedFiles.length === 0}
            className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {uploading && (
              <Spinner size="sm" className="border-white/40 border-t-white" />
            )}
            Upload{selectedFiles.length > 0 ? ` (${selectedFiles.length})` : ""}
          </button>
        </div>

        {uploadError && (
          <div className="mt-3">
            <ErrorBanner message={uploadError} />
          </div>
        )}
        {uploadWarnings.length > 0 && (
          <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <p className="font-medium">Some files had warnings:</p>
            <ul className="mt-1 list-inside list-disc space-y-0.5">
              {uploadWarnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Review action */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-4">
        <div className="text-sm text-slate-600">
          {receipts.length === 0
            ? "Upload receipts before running a review."
            : hasUnreviewed
              ? "Some receipts have not been reviewed yet."
              : "All receipts have been reviewed."}
        </div>
        <button
          onClick={handleReview}
          disabled={reviewing || receipts.length === 0}
          className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {reviewing && (
            <Spinner size="sm" className="border-white/40 border-t-white" />
          )}
          {reviewing ? "Running AI review…" : "Run AI Review"}
        </button>
      </div>

      {reviewError && <ErrorBanner message={reviewError} />}
      {reviewNotice && (
        <div className="rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {reviewNotice}
        </div>
      )}

      {/* Receipt + verdict cards */}
      {receipts.length === 0 ? (
        <EmptyState
          title="No receipts yet"
          description="Upload receipt files above to begin the review."
        />
      ) : (
        <div className="space-y-4">
          {receipts.map((receipt) => (
            <ReceiptCard
              key={receipt.id}
              receipt={receipt}
              onVerdictUpdated={handleVerdictUpdated}
            />
          ))}
        </div>
      )}
    </div>
  );
}
