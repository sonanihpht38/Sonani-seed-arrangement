// ===================== FRONTEND: shared API types =====================
// One source of truth for the list envelope shapes. Mirrors the backend:
//   Paginated<T>  <-> modules/core/pagination.py paginate_envelope()
//   DrfPage<T>    <-> DRF's default PageNumberPagination (legacy endpoints)

/** The canonical ERP list envelope ({results,total,page,page_size,total_pages}). */
export interface Paginated<T> {
  results: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** DRF's built-in pagination shape — legacy endpoints only (admin users). */
export interface DrfPage<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** Common list-query params; extra feature-specific filters allowed. */
export interface ListParams {
  page?: number;
  page_size?: number;
  q?: string;
  search?: string;
  ordering?: string;
  [key: string]: unknown;
}

/** Serialize ListParams into a query string ("" when empty). */
export function toQueryString(params?: ListParams): string {
  if (!params) return "";
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `?${s}` : "";
}
