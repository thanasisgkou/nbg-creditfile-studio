import { lazy, Suspense } from "react";
import type { Source } from "./api";
const Pdf = lazy(() => import("./PdfReader"));
export default function Reader(props: {
  url: string;
  source?: Source | null;
  title?: string;
}) {
  return (
    <Suspense
      fallback={
        <div className="page-loading" role="status">
          <span className="spinner" />
          Φόρτωση αναγνώστη PDF…
        </div>
      }
    >
      <Pdf {...props} />
    </Suspense>
  );
}
