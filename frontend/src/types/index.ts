// Domain types mirroring the FastAPI backend schemas (backend/app/schemas/*).
// Kept in sync by hand; see the API docs at http://localhost:8000/api/v1/docs.

export type VerdictValue = "compliant" | "flagged" | "rejected" | "needs_review";

export type SubmissionStatus =
  | "pending"
  | "under_review"
  | "compliant"
  | "flagged"
  | "rejected"
  | "needs_review";

export type ReceiptCategory =
  | "flight"
  | "hotel"
  | "transport"
  | "meal"
  | "registration"
  | "other";

export interface Employee {
  id: string;
  employee_id: string;
  name: string;
  grade: number;
  title: string;
  department: string;
  manager_id: string | null;
  home_base: string;
  created_at: string;
}

export interface Submission {
  id: string;
  employee_id: string;
  folder_name: string;
  trip_purpose: string;
  trip_start_date: string;
  trip_end_date: string;
  status: SubmissionStatus;
  created_at: string;
  updated_at: string;
}

export interface PolicyCitation {
  document_id: string;
  page_number: number | null;
  section: string | null;
  reason: string | null;
}

export interface QuotedClause {
  document_id: string;
  quote: string;
}

export interface Override {
  id: string;
  verdict_id: string;
  override_verdict: VerdictValue;
  reviewer_name: string;
  comment: string | null;
  created_at: string;
}

export interface Verdict {
  id: string;
  receipt_id: string;
  verdict: VerdictValue;
  reasoning: string;
  confidence: number; // 0.0 – 1.0
  policy_citations: PolicyCitation[];
  quoted_policy_clauses: QuotedClause[];
  created_at: string;
  category: string | null;
  overrides: Override[];
  effective_verdict: VerdictValue;
}

export interface Receipt {
  id: string;
  submission_id: string;
  original_filename: string;
  file_path: string;
  merchant: string | null;
  transaction_date: string | null;
  amount: number | null;
  currency: string;
  category: string | null;
  created_at: string;
}

export interface ReceiptWithVerdict extends Receipt {
  raw_extracted_text: string | null;
  verdict: Verdict | null;
}

export interface SubmissionDetail extends Submission {
  employee: Employee | null;
  receipts: ReceiptWithVerdict[];
}

export interface ReceiptUploadResponse {
  submission_id: string;
  receipts: Receipt[];
  warnings: string[];
}

export interface ReviewResponse {
  submission_id: string;
  status: SubmissionStatus;
  reviewed: number;
  verdicts: Verdict[];
}

export interface SubmissionCreatePayload {
  employee_id: string;
  trip_purpose: string;
  trip_start_date: string;
  trip_end_date: string;
  folder_name?: string;
}

export interface OverridePayload {
  override_verdict: VerdictValue;
  reviewer_name: string;
  comment?: string;
}

export interface PolicySearchResult {
  document_id: string;
  page_number: number | null;
  section: string | null;
  chunk_text: string;
  similarity: number;
  confidence: string; // high | medium | low
}

export interface PolicySearchResponse {
  query: string;
  confidence: string;
  results: PolicySearchResult[];
}
