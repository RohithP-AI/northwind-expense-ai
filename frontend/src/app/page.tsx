"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState, ErrorState } from "@/components/States";
import { LoadingState } from "@/components/Spinner";
import { api, ApiError, type SubmissionFilters } from "@/lib/api";
import { formatDate, formatDateRange, humanize } from "@/lib/format";
import { STATUS_FILTER_OPTIONS } from "@/lib/status";
import type { Employee, Submission } from "@/types";

export default function DashboardPage() {
  const router = useRouter();
  const [employees, setEmployees] = useState<Employee[]>([]);
  // Employees only label rows and populate the filter; their fetch is tracked
  // separately so a failure never blocks the submissions table.
  const [employeesFailed, setEmployeesFailed] = useState(false);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [employeeId, setEmployeeId] = useState("");
  const [status, setStatus] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const employeeNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const e of employees) map.set(e.employee_id, e.name);
    return map;
  }, [employees]);

  // Employees load once on mount, independently of submissions. A failure is
  // swallowed (employeesFailed flag) so the submissions table still renders;
  // the filter then falls back to a disabled state and rows show raw ids.
  const loadEmployees = useCallback(async () => {
    setEmployeesFailed(false);
    try {
      setEmployees(await api.listEmployees());
    } catch {
      setEmployeesFailed(true);
    }
  }, []);

  // Submissions reload whenever the filters change. Only a failure of this
  // request drives the table's error state.
  const loadSubmissions = useCallback(async () => {
    setLoading(true);
    setError(null);
    const filters: SubmissionFilters = {
      employee_id: employeeId || undefined,
      status: status || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    };
    try {
      setSubmissions(await api.listSubmissions(filters));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load submissions.");
    } finally {
      setLoading(false);
    }
  }, [employeeId, status, dateFrom, dateTo]);

  useEffect(() => {
    loadEmployees();
  }, [loadEmployees]);

  useEffect(() => {
    loadSubmissions();
  }, [loadSubmissions]);

  function resetFilters() {
    setEmployeeId("");
    setStatus("");
    setDateFrom("");
    setDateTo("");
  }

  const hasFilters = employeeId || status || dateFrom || dateTo;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Submissions</h1>
          <p className="text-sm text-slate-500">
            Expense submissions awaiting or completed review.
          </p>
        </div>
        <Link
          href="/submissions/new"
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
        >
          New Submission
        </Link>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-5">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-500">
            Employee
          </label>
          <select
            value={employeeId}
            onChange={(e) => setEmployeeId(e.target.value)}
            disabled={employeesFailed}
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-slate-500 focus:outline-none disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
          >
            <option value="">
              {employeesFailed ? "Employees unavailable" : "All employees"}
            </option>
            {employees.map((e) => (
              <option key={e.employee_id} value={e.employee_id}>
                {e.name} ({e.employee_id})
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-500">
            Status
          </label>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
          >
            <option value="">All statuses</option>
            {STATUS_FILTER_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {humanize(s)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-500">
            Trip from
          </label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-500">
            Trip to
          </label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
          />
        </div>
        <div className="flex items-end">
          <button
            onClick={resetFilters}
            disabled={!hasFilters}
            className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            Clear filters
          </button>
        </div>
      </div>

      {/* Table / states */}
      {loading ? (
        <LoadingState label="Loading submissions…" />
      ) : error ? (
        <ErrorState message={error} onRetry={loadSubmissions} />
      ) : submissions.length === 0 ? (
        <EmptyState
          title="No submissions found"
          description={
            hasFilters
              ? "No submissions match the current filters."
              : "Create your first expense submission to get started."
          }
          action={
            <Link
              href="/submissions/new"
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
            >
              New Submission
            </Link>
          }
        />
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">Employee</th>
                <th className="px-4 py-3 font-medium">Trip purpose</th>
                <th className="px-4 py-3 font-medium">Trip dates</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {submissions.map((s) => (
                <tr
                  key={s.id}
                  onClick={() => router.push(`/submissions/${s.id}`)}
                  className="cursor-pointer hover:bg-slate-50"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-900">
                      {employeeNames.get(s.employee_id) ?? s.employee_id}
                    </div>
                    <div className="text-xs text-slate-400">{s.employee_id}</div>
                  </td>
                  <td className="max-w-xs px-4 py-3 text-slate-700">
                    <span className="line-clamp-2">{s.trip_purpose}</span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                    {formatDateRange(s.trip_start_date, s.trip_end_date)}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge value={s.status} />
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                    {formatDate(s.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
