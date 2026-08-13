// Plate images and Excel exports live under MEDIA_ROOT and are addressed as
// /media/... — the path the backend stores and returns.
//
// That path only works when whatever serves the SPA also routes /media to
// Django. A deployment that proxies just /api (the common case) answers
// /media/... from its SPA fallback instead: HTTP 200, Content-Type text/html,
// the index page — so every <img> breaks while the rest of the app works.
//
// Sending them through /api/media/... instead makes them follow the proxy rule
// that must already exist, since the app cannot function without it. Django
// serves both prefixes, so this is safe in every environment, including the dev
// server (Vite proxies /api and /media alike).
export function mediaUrl(url: string): string;
export function mediaUrl(url: string | null | undefined): string | undefined;
export function mediaUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  // Only rewrite root-relative media paths. Absolute URLs (http://…) and
  // anything already under /api are passed through untouched.
  return url.startsWith("/media/") ? `/api${url}` : url;
}
