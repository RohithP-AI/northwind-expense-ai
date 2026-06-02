import SubmissionDetailClient from "./SubmissionDetailClient";

// Server component wrapper. `output: "export"` requires `generateStaticParams`
// for dynamic routes, and Next treats an empty result as "missing", so we emit
// one placeholder route. The page is fully client-rendered and reads its
// submission id from the URL at runtime, so in-app navigation from the
// dashboard renders any real id correctly. (A hard load/refresh of a detail URL
// on a static host needs an SPA rewrite — see README deployment notes.)
export function generateStaticParams() {
  return [{ id: "_" }];
}

// Allow client-side navigation to ids that weren't pre-rendered at build time.
export const dynamicParams = true;

export default function SubmissionDetailPage() {
  return <SubmissionDetailClient />;
}
