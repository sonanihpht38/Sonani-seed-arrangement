// Feature API layer for the RBAC reads the app makes at runtime: the navigation
// catalogue that builds the sidebar, and the current user's column visibility.
// Roles and permissions are administered from the Django admin, not over the API.

import { api } from "../../api/client";
import type { ModuleGroup, VisibleColumnsMap } from "./types";

export const accessApi = {
  catalogue: () => api.get<ModuleGroup[]>("/access/catalogue/"),

  /** The CURRENT user's visible columns for one form's grid. Consumed by every
   *  DataGrid screen via useVisibleColumns(). */
  visibleColumns: (formCode: string) =>
    api.get<VisibleColumnsMap>(`/access/visible-columns/?form=${formCode}`),
};
