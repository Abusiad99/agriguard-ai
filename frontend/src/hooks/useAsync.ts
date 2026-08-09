import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/types/api";

export type AsyncState<T> =
  | { status: "loading" }
  | { status: "error"; error: ApiError | Error }
  | { status: "success"; data: T };

/**
 * Minimal, dependency-free async-data hook (deliberately not adding a data-fetching
 * library dependency for a project this size). Re-fetches whenever `deps` change,
 * and ignores results from stale requests if the component re-renders mid-flight.
 */
export function useAsync<T>(fetcher: () => Promise<T>, deps: React.DependencyList): AsyncState<T> & {
  refetch: () => void;
} {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });
  const requestIdRef = useRef(0);

  const run = useCallback(() => {
    const requestId = ++requestIdRef.current;
    setState({ status: "loading" });
    fetcher()
      .then((data) => {
        if (requestIdRef.current === requestId) setState({ status: "success", data });
      })
      .catch((error) => {
        if (requestIdRef.current === requestId) setState({ status: "error", error });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run]);

  return { ...state, refetch: run };
}

export function errorMessage(error: ApiError | Error): string {
  if (error instanceof ApiError) return error.message;
  return error.message || "An unexpected error occurred.";
}
