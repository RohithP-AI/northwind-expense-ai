export type ExpenseStatus = "pending" | "under_review" | "approved" | "rejected";
export type ReviewRecommendation = "approve" | "reject" | "manual_review";
export type UserRole = "employee" | "manager" | "finance" | "admin";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
}

export interface Expense {
  id: string;
  submitted_by: string;
  title: string;
  description: string | null;
  amount: number;
  currency: string;
  category: string;
  expense_date: string;
  receipt_url: string | null;
  status: ExpenseStatus;
  created_at: string;
  updated_at: string;
}

export interface ExpenseReview {
  id: string;
  expense_id: string;
  risk_score: number;
  flags: string[] | null;
  ai_summary: string | null;
  recommendation: ReviewRecommendation;
  reviewed_at: string;
}
