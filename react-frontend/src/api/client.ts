// ===================== FRONTEND: transport layer =====================
// ONE place that knows how to talk HTTP: base URL, auth header, token refresh,
// error shape. Every feature calls this.
//
// Silent refresh: on a 401 we try ONCE to mint a new access token from the
// refresh token, then replay the original request. Concurrent 401s share a
// single in-flight refresh (single-flight) so we never fire N refreshes at once.
// If refresh fails, tokens are cleared and an "auth:expired" event is dispatched
// so the auth layer can drop the user and the router can bounce to /login.

import { tokenStore } from "./tokenStore";

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let refreshInFlight: Promise<string | null> | null = null;

function refreshAccessToken(): Promise<string | null> {
  const refresh = tokenStore.refresh();
  if (!refresh) return Promise.resolve(null);

  if (!refreshInFlight) {
    refreshInFlight = fetch(`${BASE_URL}/auth/token/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    })
      .then(async (res) => {
        if (!res.ok) return null;
        const data = (await res.json()) as { access: string };
        tokenStore.set(data.access);
        return data.access;
      })
      .catch(() => null)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

async function request<T>(path: string, options: RequestInit = {}, allowRetry = true): Promise<T> {
  const token = tokenStore.access();
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  // Access token likely expired — refresh once and replay (never for the token
  // endpoints themselves, to avoid loops).
  if (res.status === 401 && allowRetry && !path.startsWith("/auth/token")) {
    const newToken = await refreshAccessToken();
    if (newToken) return request<T>(path, options, false);
    tokenStore.clear();
    window.dispatchEvent(new Event("auth:expired"));
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, (body as { detail?: string }).detail ?? res.statusText);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

// Multipart POST (file upload). Same Bearer auth + single-flight refresh as
// request(), but we DON'T set Content-Type — the browser adds the multipart
// boundary itself. Used for datasheet uploads (e.g. seed import).
async function requestForm<T>(path: string, form: FormData, allowRetry = true): Promise<T> {
  const token = tokenStore.access();
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    body: form,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });

  if (res.status === 401 && allowRetry) {
    const newToken = await refreshAccessToken();
    if (newToken) return requestForm<T>(path, form, false);
    tokenStore.clear();
    window.dispatchEvent(new Event("auth:expired"));
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, (body as { detail?: string }).detail ?? res.statusText);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

// POST that returns a binary Blob (file download), with the same auth + refresh.
async function requestBlob(path: string, body: unknown, allowRetry = true): Promise<Blob> {
  const token = tokenStore.access();
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });

  if (res.status === 401 && allowRetry) {
    const newToken = await refreshAccessToken();
    if (newToken) return requestBlob(path, body, false);
    tokenStore.clear();
    window.dispatchEvent(new Event("auth:expired"));
  }

  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new ApiError(res.status, (b as { detail?: string }).detail ?? res.statusText);
  }
  return res.blob();
}

export const api = {
  get: <T>(p: string) => request<T>(p),
  post: <T>(p: string, body: unknown) =>
    request<T>(p, { method: "POST", body: JSON.stringify(body) }),
  postForm: <T>(p: string, form: FormData) => requestForm<T>(p, form),
  postBlob: (p: string, body: unknown) => requestBlob(p, body),
  put: <T>(p: string, body: unknown) =>
    request<T>(p, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(p: string, body: unknown) =>
    request<T>(p, { method: "PATCH", body: JSON.stringify(body) }),
  del: <T>(p: string) => request<T>(p, { method: "DELETE" }),
};
