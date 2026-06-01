// Tailwind class strings for verdict / submission-status badges.
// Full literal class strings (no interpolation) so Tailwind's content scanner
// keeps them in the production build.

export interface BadgeStyle {
  /** Badge pill classes (background + text + border). */
  badge: string;
  /** A subtle accent border used on cards (left border color). */
  accentBorder: string;
}

const NEUTRAL: BadgeStyle = {
  badge: "bg-slate-100 text-slate-700 border-slate-200",
  accentBorder: "border-l-slate-300",
};

// Verdict + status share a vocabulary, so one map covers both.
const STYLES: Record<string, BadgeStyle> = {
  // verdicts / terminal statuses
  compliant: {
    badge: "bg-green-100 text-green-800 border-green-300",
    accentBorder: "border-l-green-500",
  },
  flagged: {
    badge: "bg-amber-100 text-amber-800 border-amber-300",
    accentBorder: "border-l-amber-500",
  },
  rejected: {
    badge: "bg-red-100 text-red-800 border-red-300",
    accentBorder: "border-l-red-500",
  },
  needs_review: {
    badge: "bg-blue-100 text-blue-800 border-blue-300",
    accentBorder: "border-l-blue-500",
  },
  // intermediate submission statuses
  pending: {
    badge: "bg-slate-100 text-slate-700 border-slate-200",
    accentBorder: "border-l-slate-300",
  },
  under_review: {
    badge: "bg-indigo-100 text-indigo-800 border-indigo-300",
    accentBorder: "border-l-indigo-500",
  },
};

export function statusStyle(value: string | null | undefined): BadgeStyle {
  if (!value) return NEUTRAL;
  return STYLES[value] ?? NEUTRAL;
}

// Confidence (high | medium | low) from policy search.
const CONFIDENCE_STYLES: Record<string, string> = {
  high: "bg-green-100 text-green-800 border-green-300",
  medium: "bg-amber-100 text-amber-800 border-amber-300",
  low: "bg-slate-100 text-slate-700 border-slate-200",
};

export function confidenceStyle(value: string | null | undefined): string {
  if (!value) return CONFIDENCE_STYLES.low;
  return CONFIDENCE_STYLES[value] ?? CONFIDENCE_STYLES.low;
}

// The vocabulary a reviewer can choose when overriding a verdict.
export const VERDICT_OPTIONS = [
  "compliant",
  "flagged",
  "rejected",
  "needs_review",
] as const;

// Submission status filter options for the dashboard.
export const STATUS_FILTER_OPTIONS = [
  "pending",
  "under_review",
  "compliant",
  "flagged",
  "rejected",
  "needs_review",
] as const;
