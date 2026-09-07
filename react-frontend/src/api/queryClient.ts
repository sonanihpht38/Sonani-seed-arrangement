// Shared React Query client.
//
// Why this matters at scale: without a client cache every component mount
// re-fetches, so users flipping between screens hammer the API with redundant
// GETs. React Query dedupes in-flight requests, serves cached data instantly,
// refetches in the background, and retries transient failures with backoff.
//
// Global error handling: any query/mutation error surfaces as a toast, so
// screens don't each reimplement error display. 401s are handled by the
// transport layer (silent refresh), so we suppress those here.

import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { ApiError } from "./client";
import { notify } from "../lib/notify";

function toast(error: unknown) {
  if (error instanceof ApiError && error.status === 401) return; // handled by refresh flow
  notify.error(error instanceof Error ? error.message : "Something went wrong");
}

/**
 * The same toast, unless the query asked to be left alone with `meta.quiet`.
 *
 * Some failures are an expected state rather than a fault, and the screen
 * already renders them. Finalization is the case that prompted this: it opens
 * with a job id kept in sessionStorage from the Result screen, and a job only
 * lives 24 hours, so returning to the screen the next day asks for one that is
 * gone. The API correctly answers 404, the screen correctly shows "Nothing to
 * finalize" — and a red "job not found" toast appeared over the top of it,
 * telling the user something had broken when nothing had.
 *
 * Only for a query that HANDLES the error itself. A screen that shows nothing
 * must not be quiet, or a real fault would vanish silently.
 */
function toastUnlessQuiet(error: unknown, query: { meta?: Record<string, unknown> }) {
  if (query?.meta?.quiet) return;
  toast(error);
}

export const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: toastUnlessQuiet }),
  mutationCache: new MutationCache({ onError: toast }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status < 500 && error.status !== 0) {
          return false;
        }
        return failureCount < 2;
      },
    },
    mutations: { retry: false },
  },
});
