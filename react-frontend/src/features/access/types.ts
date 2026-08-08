// Mirror of the access module DTOs (navigation catalogue + column visibility).

export interface Form {
  id: number;
  code: string;
  name: string;
  icon: string;
  route: string;
  sort_order: number;
  is_active: boolean;
}

export interface ModuleGroup {
  id: number;
  code: string;
  name: string;
  icon: string;
  sort_order: number;
  forms: Form[];
}

/** {column_key: visible} for the CURRENT user on one form's grid. A key absent
 *  from this map isn't managed by column permissions and should always show. */
export type VisibleColumnsMap = Record<string, boolean>;
