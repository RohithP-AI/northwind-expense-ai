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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const filters: SubmissionFilters = {
      employee_id: employeeId || undefined,
      status: status || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    };
    try {
      const [emps, subs] = await Promise.all([
        // Employees are only needed once, but refetching is cheap and keeps the
        // name map fresh; ignore employee errors so the table still renders.
        employees.length ? Promise.resolve(employees) : api.listEmployees(),
        api.listSubmissions(filters),
      ]);
      setEmployees(emps);
      setSubmissions(subs);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load submissions.");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employeeId, status, dateFrom, dateTo]);

  useEffect(() => {
    load();
  }, [load]);

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
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
          >
            <option value="">All employees</option>
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
        <ErrorState message={error} onRetry={load} />
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
