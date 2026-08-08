// ===================== FRONTEND: auth API layer =====================
// Talks to SimpleJWT (/auth/token) and /auth/me. Token persistence lives in
// tokenStore; components never touch tokens directly.

import { api } from "../../api/client";
import { tokenStore } from "../../api/tokenStore";

export interface TokenPair {
  access: string;
  refresh: string;
}

export interface RoleRef {
  id: number;
  code: string;
  name: string;
}

export type FormPermission = {
  view: boolean;
  create: boolean;
  edit: boolean;
  delete: boolean;
  export: boolean;
  // Aliases exposed by the backend: save == create, update == edit.
  save: boolean;
  update: boolean;
};

export interface Me {
  id: number;
  username: string;
  email: string;
  full_name: string;
  tenant_id: number | null;
  is_superuser: boolean;
  roles: RoleRef[];
  permissions: Record<string, FormPermission>;
}

/** True if we still hold an access token (used to decide whether to load /me). */
export function hasToken(): boolean {
  return Boolean(tokenStore.access());
}

export const authApi = {
  login: async (username: string, password: string): Promise<TokenPair> => {
    const tokens = await api.post<TokenPair>("/auth/token", { username, password });
    tokenStore.set(tokens.access, tokens.refresh);
    return tokens;
  },

  me: () => api.get<Me>("/auth/me"),

  register: (input: {
    username: string; email: string; password: string;
    first_name?: string; last_name?: string;
  }) => api.post<{ detail: string }>("/auth/register", input),

  forgotPassword: (email: string) =>
    api.post<{ detail: string }>("/auth/forgot-password", { email }),

  resetPassword: (uid: string, token: string, newPassword: string) =>
    api.post<{ detail: string }>("/auth/reset-password", { uid, token, new_password: newPassword }),

  logout: () => tokenStore.clear(),
};
