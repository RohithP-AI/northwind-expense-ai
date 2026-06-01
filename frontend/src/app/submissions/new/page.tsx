"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ErrorBanner, ErrorState } from "@/components/States";
import { LoadingState, Spinner } from "@/components/Spinner";
import { api, ApiError } from "@/lib/api";
import type { Employee } from "@/types";

export default function NewSubmissionPage() {
  const router = useRouter();
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [employeeId, setEmployeeId] = useState("");
  const [tripPurpose, setTripPurpose] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  async function loadEmployees() {
    setLoading(true);
    setLoadError(null);
    try {
      setEmployees(await api.listEmployees());
    } catch (err) {
      setLoadError(
        err instanceof ApiError ? err.message : "Failed to load employees.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadEmployees();
  }, []);

  function validate(): string | null {
    if (!employeeId) return "Please select an employee.";
    if (!tripPurpose.trim()) return "Please enter a trip purpose.";
    if (!startDate) return "Please select a trip start date.";
    if (!endDate) return "Please select a trip end date.";
    if (endDate < startDate) return "End date must be on or after the start date.";
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const validationError = validate();
    if (validationError) {
      setSubmitError(validationError);
      return;
    }
    setSubmitError(null);
    setSubmitting(true);
    try {
      const submission = await api.createSubmission({
        employee_id: employeeId,
        trip_purpose: tripPurpose.trim(),
        trip_start_date: startDate,
        trip_end_date: endDate,
      });
      router.push(`/submissions/${submission.id}`);
    } catch (err) {
      setSubmitError(
        err instanceof ApiError ? err.message : "Failed to create submission.",
      );
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <Link href="/" className="text-sm text-slate-500 hover:text-slate-800">
          ← Back to submissions
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900">
          New submission
        </h1>
        <p className="text-sm text-slate-500">
          Create an expense submission for an employee trip.
        </p>
      </div>

      {loading ? (
        <LoadingState label="Loading employees…" />
      ) : loadError ? (
        <ErrorState message={loadError} onRetry={loadEmployees} />
      ) : (
        <form
          onSubmit={handleSubmit}
          className="space-y-5 rounded-lg border border-slate-200 bg-white p-6"
        >
          {submitError && <ErrorBanner message={submitError} />}

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Employee <span className="text-red-500">*</span>
            </label>
            <select
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
            >
              <option value="">Select an employee…</option>
              {employees.map((emp) => (
                <option key={emp.employee_id} value={emp.employee_id}>
                  {emp.name} — {emp.title} ({emp.employee_id})
                </option>
              ))}
            </select>
            {employees.length === 0 && (
              <p className="mt-1 text-xs text-amber-600">
                No employees found. Seed employees on the backend first.
              </p>
            )}
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Trip purpose <span className="text-red-500">*</span>
            </label>
            <textarea
              value={tripPurpose}
              onChange={(e) => setTripPurpose(e.target.value)}
              rows={2}
              placeholder="e.g. Quarterly client review in Denver"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                Trip start <span className="text-red-500">*</span>
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                Trip end <span className="text-red-500">*</span>
              </label>
              <input
                type="date"
                value={endDate}
                min={startDate || undefined}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <Link
              href="/"
              className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </Link>
            <button
              type="submit"
              disabled={submitting}
              className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {submitting && (
                <Spinner size="sm" className="border-white/40 border-t-white" />
              )}
              Create submission
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
