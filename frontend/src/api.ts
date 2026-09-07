export const BASE = "/api/v1";
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}
export async function api<T = any>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(BASE + path, {
    ...init,
    headers:
      init?.body instanceof FormData
        ? init.headers
        : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : response.status === 422
          ? "Ελέγξτε ότι συμπληρώσατε σωστά όλα τα απαιτούμενα στοιχεία."
          : "Η ενέργεια δεν ολοκληρώθηκε. Δοκιμάστε ξανά.";
    throw new ApiError(detail, response.status);
  }
  return response.json();
}
export const post = <T = any>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "POST",
    body: body instanceof FormData ? body : JSON.stringify(body ?? {}),
  });
export const command = (expected: string) => ({
  expected,
  request_id: crypto.randomUUID(),
});
export const kindLabel = (kind: string) =>
  kind === "application" ? "Αίτηση χρηματοδότησης" : "Οικονομικές καταστάσεις";
export function valueLabel(value: unknown, money = false): string {
  if (value === null || value === undefined || value === "") return "—";
  if (money && Number.isFinite(Number(value)))
    return (
      new Intl.NumberFormat("el-GR", {
        maximumFractionDigits: 2,
        minimumFractionDigits: Number(value) % 1 ? 2 : 0,
      }).format(Number(value)) + " €"
    );
  return String(value);
}
export const dateLabel = (value: string) =>
  new Date(value).toLocaleDateString("el-GR", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
export function canonicalMoney(input: string): string {
  const value = input.trim().replace(/\s|€/g, "");
  if (/^-?\d+(\.\d{1,2})?$/.test(value)) return value;
  if (/^-?(\d{1,3}(\.\d{3})+|\d+)(,\d{1,2})?$/.test(value))
    return value.replaceAll(".", "").replace(",", ".");
  throw new Error("Γράψτε ποσό όπως 750.000,00 ή 750000.00.");
}
export interface Source {
  document_id: string;
  document_name?: string;
  page: number;
  block_id: string;
  quote: string;
  excerpt?: string;
  rectangles?: number[][];
  value_rectangles?: number[][];
  page_width?: number;
  page_height?: number;
  geometry_status?: string;
}
export interface FieldValue {
  id: string;
  name: string;
  label: string;
  kind: string;
  money: boolean;
  normalized_value: unknown;
  raw_value?: string;
  status: string;
  review_status?: string;
  review_reason?: string;
  uncertainty?: string;
  eligible: boolean;
  eligibility_reason: string;
  sources: Source[];
  approved_for_credit_memo?: boolean;
}
export interface CaseRow {
  id: string;
  name: string;
  created: string;
  run_id: string | null;
  error?: string;
  summary: {
    pending: number;
    reviewed: number;
    conflicts: number;
    draft: boolean;
    state: string;
  } | null;
}
export interface Workspace {
  case: CaseRow;
  run_id: string;
  fields: FieldValue[];
  report: any;
  runs: { id: string; created: string; mode: string }[];
  mode: string;
  errors: string[];
  reviews: any[];
  versions: any[];
  questions: string[];
  execution_mode: string;
}
