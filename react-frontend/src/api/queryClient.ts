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

export const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: toast }),
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
