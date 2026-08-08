// ===================== Column-level RBAC (frontend) =====================
// One hook + one filter, reused by every DataGrid screen: fetch which columns
// the current user may see on a form's grid, then drop the hidden ones before
// handing columnDefs to <DataGrid>. A column with no colId/field is unmanaged
// (e.g. an Actions button column) and always shows; a column whose key isn't
// registered in the grid-column master also always shows — filtering only ever
// removes columns that ARE registered AND not granted to this user.

import { useQuery } from "@tanstack/react-query";
import type { ColDef } from "ag-grid-community";
import { accessApi } from "./accessApi";
import type { VisibleColumnsMap } from "./types";

export function useVisibleColumns(formCode: string) {
  return useQuery({
    queryKey: ["visible-columns", formCode],
    queryFn: () => accessApi.visibleColumns(formCode),
  });
}

export function applyColumnVisibility<T>(
  colDefs: ColDef<T>[],
  map: VisibleColumnsMap | undefined,
): ColDef<T>[] {
  if (!map) return colDefs;
  return colDefs.filter((c) => {
    const key = c.colId ?? (typeof c.field === "string" ? c.field : undefined);
    if (!key) return true;
    if (!(key in map)) return true;
    return map[key];
  });
}
