import type {
  Employee,
  OverridePayload,
  PolicySearchResponse,
  ReceiptUploadResponse,
  ReviewResponse,
  Submission,
  SubmissionCreatePayload,
  SubmissionDetail,
  Verdict,
} from "@/types";

// The API base URL already includes the /api/v1 prefix.
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

/** Error raised for any non-2xx response or network failure. `status === 0`
 *  means the request never reached the server (backend down / CORS / offline). */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
  /** True when the backend was unreachable (as opposed to returning an error). */
  get isNetworkError() {
    return this.status === 0;
  }
}

async function extractErrorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    const detail = (data as { detail?: unknown })?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      // FastAPI/pydantic validation errors: [{ loc, msg, ... }]
      return detail
        .map((e) => (e as { msg?: string })?.msg ?? JSON.stringify(e))
        .join("; ");
    }
    if (detail) return JSON.stringify(detail);
    return JSON.stringify(data);
  } catch {
    return res.statusText || `Request failed (HTTP ${res.status})`;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(
      `Cannot reach the API at ${API_BASE_URL}. Is the backend running?`,
      0,
    );
  }
  if (!res.ok) {
    throw new ApiError(await extractErrorMessage(res), res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function jsonRequest<T>(path: string, method: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function queryString(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, value);
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export interface SubmissionFilters {
  employee_id?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  // Index signature so the object is assignable to the query-string builder.
  [key: string]: string | undefined;
}

export const api = {
  // ── Employees ──────────────────────────────────────────────────────────
  listEmployees: (department?: string) =>
    request<Employee[]>(`/employees/${queryString({ department })}`),

  getEmployee: (employeeId: string) =>
    request<Employee>(`/employees/${encodeURIComponent(employeeId)}`),

  // ── Submissions ────────────────────────────────────────────────────────
  listSubmissions: (filters: SubmissionFilters = {}) =>
    request<Submission[]>(`/submissions/${queryString(filters)}`),

  createSubmission: (payload: SubmissionCreatePayload) =>
    jsonRequest<Submission>(`/submissions/`, "POST", payload),

  getSubmission: (id: string) =>
    request<SubmissionDetail>(`/submissions/${id}`),

  // ── Receipts ───────────────────────────────────────────────────────────
  uploadReceipts: (id: string, files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    // No explicit Content-Type: the browser sets the multipart boundary.
    return request<ReceiptUploadResponse>(`/submissions/${id}/receipts`, {
      method: "POST",
      body: form,
    });
  },

  // ── Review ─────────────────────────────────────────────────────────────
  reviewSubmission: (id: string) =>
    jsonRequest<ReviewResponse>(`/submissions/${id}/review`, "POST"),

  // ── Verdicts / overrides ───────────────────────────────────────────────
  getReceiptVerdict: (receiptId: string) =>
    request<Verdict>(`/receipts/${receiptId}/verdict`),

  overrideVerdict: (verdictId: string, payload: OverridePayload) =>
    jsonRequest<Verdict>(`/verdicts/${verdictId}/override`, "POST", payload),

  // ── Policy search ──────────────────────────────────────────────────────
  policySearch: (query: string, topK = 5) =>
    jsonRequest<PolicySearchResponse>(`/policy/search`, "POST", {
      query,
      top_k: topK,
    }),
};
