// ===================== FRONTEND: resource API factory =====================
// One call produces the standard CRUD client for a backend TenantCrudViewSet:
//
//   export const departmentsApi = makeResourceApi<Department>("/hr/departments");
//
// list() returns the canonical Paginated<T> envelope; the rest are plain CRUD.

import { api } from "./client";
import type { ListParams, Paginated } from "./types";
import { toQueryString } from "./types";

export interface ResourceApi<T, TInput = Partial<T>> {
  basePath: string;
  list: (params?: ListParams) => Promise<Paginated<T>>;
  get: (id: number) => Promise<T>;
  create: (body: TInput) => Promise<T>;
  update: (id: number, body: Partial<TInput>) => Promise<T>;
  remove: (id: number) => Promise<void>;
}

export function makeResourceApi<T, TInput = Partial<T>>(basePath: string): ResourceApi<T, TInput> {
  return {
    basePath,
    list: (params) => api.get<Paginated<T>>(`${basePath}/${toQueryString(params)}`),
    get: (id) => api.get<T>(`${basePath}/${id}/`),
    create: (body) => api.post<T>(`${basePath}/`, body),
    update: (id, body) => api.patch<T>(`${basePath}/${id}/`, body),
    remove: (id) => api.del<void>(`${basePath}/${id}/`),
  };
}
