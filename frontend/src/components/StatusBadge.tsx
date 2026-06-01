import { humanize } from "@/lib/format";
import { confidenceStyle, statusStyle } from "@/lib/status";

interface StatusBadgeProps {
  value: string | null | undefined;
  className?: string;
}

/** Badge for a verdict or submission status. */
export function StatusBadge({ value, className = "" }: StatusBadgeProps) {
  const style = statusStyle(value);
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${style.badge} ${className}`}
    >
      {humanize(value)}
    </span>
  );
}

/** Badge for a policy-search confidence level (high / medium / low). */
export function ConfidenceBadge({ value, className = "" }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${confidenceStyle(value)} ${className}`}
    >
      {humanize(value)}
    </span>
  );
}
