// Single source of truth for JWT tokens. Persisted in localStorage so a page
// reload keeps the session; both the transport layer (client.ts) and the auth
// feature read/write through here (no window globals).

const ACCESS_KEY = "tf_access";
const REFRESH_KEY = "tf_refresh";

export const tokenStore = {
  access: (): string | null => localStorage.getItem(ACCESS_KEY),
  refresh: (): string | null => localStorage.getItem(REFRESH_KEY),
  set(access: string, refresh?: string) {
    localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};
