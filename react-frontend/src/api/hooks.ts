// ===================== FRONTEND: shared list-query hook =====================
// The standard way to fetch a paginated list. keepPreviousData keeps the grid
// populated while the next page/search loads (no flicker).

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "./client";
import type { ListParams, Paginated } from "./types";
import { toQueryString } from "./types";

export function useListQuery<T>(key: string, path: string, params?: ListParams) {
  return useQuery<Paginated<T>>({
    queryKey: [key, params],
    queryFn: () => api.get<Paginated<T>>(`${path}${toQueryString(params)}`),
    placeholderData: keepPreviousData,
  });
}
