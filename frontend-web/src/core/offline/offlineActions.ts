import { useCallback } from "react";
import { ApiClientError } from "../api/apiClient";
import { useOffline } from "./offlineContext";
import type { EnqueueInput } from "./queue";

/**
 * «آنلاین اگر شد، وگرنه در صف» — the one place that decides whether a write
 * goes to the server now or to the queue for later.
 *
 * Rules, in order:
 *
 * 1. Known-offline → queue it immediately; do not waste 30 s on a timeout.
 * 2. Online → try the real call first. A success is always better than a
 *    queued promise: the technician sees the server's answer.
 * 3. The call failed *because of the network* → queue it and report success
 *    to the caller, flagged `queued`.
 * 4. The call failed because the server said no (4xx that is not 408/429) →
 *    rethrow. Queueing a validation error would replay a doomed request
 *    forever and hide the real problem.
 */

export interface OfflineRunResult<T> {
  queued: boolean;
  result?: T;
}

/** A failure that means "we could not reach the server", not "no". */
export const isConnectivityFailure = (error: unknown): boolean => {
  if (error instanceof ApiClientError) {
    return (
      error.isNetworkError ||
      error.status === 0 ||
      error.status === 408 ||
      error.status === 429 ||
      error.status >= 500
    );
  }
  return error instanceof TypeError;
};

export function useOfflineMutation(): <T>(
  options: { online: () => Promise<T>; offline: EnqueueInput },
) => Promise<OfflineRunResult<T>> {
  const { isOnline, enqueue } = useOffline();

  return useCallback(
    async <T,>({
      online,
      offline,
    }: {
      online: () => Promise<T>;
      offline: EnqueueInput;
    }): Promise<OfflineRunResult<T>> => {
      if (!isOnline) {
        await enqueue(offline);
        return { queued: true };
      }
      try {
        return { queued: false, result: await online() };
      } catch (error) {
        if (!isConnectivityFailure(error)) throw error;
        await enqueue(offline);
        return { queued: true };
      }
    },
    [enqueue, isOnline],
  );
}
