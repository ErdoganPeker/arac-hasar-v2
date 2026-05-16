'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import type { InspectionStatusResponse } from '@arac-hasar/types';
import { classifyApiError, getInspectionStatus } from './api';

export interface PollingState {
  data: InspectionStatusResponse | null;
  error: string | null;
  loading: boolean;
  attempts: number;
  /** Hit the wall-clock budget without reaching a terminal status. */
  timedOut: boolean;
  /**
   * Polling stopped due to too many consecutive errors but the inspection
   * itself may still complete on the backend — the UI should offer a
   * "check again" button instead of an "internet down" error.
   */
  paused: boolean;
}

export interface UseInspectionPollingOptions {
  /** Initial polling interval in ms. Default 1500. */
  intervalMs?: number;
  /**
   * Max polling duration in ms before giving up.
   * Default 180_000 (3 min) — large enough for 20-image async batches.
   */
  maxDurationMs?: number;
  /** Max single interval after exponential backoff. Default 8000. */
  maxIntervalMs?: number;
  /** Disable polling entirely. */
  enabled?: boolean;
}

interface PollingReturn extends PollingState {
  /** Resume polling after a pause/timeout (manual retry from the UI). */
  retry: () => void;
}

/**
 * Polls /v1/inspections/{id} every `intervalMs` until status is
 * `completed` or `failed` (or the max duration / consecutive-error budget
 * elapses).
 *
 * Error policy:
 *  - 401 / 403 / 404                → fatal: stop, surface translated error.
 *  - Network / timeout / 5xx        → transient: keep polling with backoff.
 *                                      After 8 consecutive failures, pause
 *                                      and let the user manually retry.
 *  - User-cancelled (AbortError)    → silent: do not stamp state.
 */
export function useInspectionPolling(
  inspectionId: string | null,
  opts: UseInspectionPollingOptions = {},
): PollingReturn {
  const {
    intervalMs = 1_500,
    maxDurationMs = 180_000,
    maxIntervalMs = 8_000,
    enabled = true,
  } = opts;
  const tResult = useTranslations('inspect.result');
  const tNetwork = useTranslations('errors.network');
  const tHttp = useTranslations('errors.http');

  const [state, setState] = useState<PollingState>({
    data: null,
    error: null,
    loading: !!inspectionId && enabled,
    attempts: 0,
    timedOut: false,
    paused: false,
  });

  // Bumping this triggers a re-poll (manual retry button).
  const [retryNonce, setRetryNonce] = useState(0);

  const startedAtRef = useRef<number>(0);
  const cancelledRef = useRef<boolean>(false);

  const retry = useCallback(() => {
    setRetryNonce((n) => n + 1);
  }, []);

  useEffect(() => {
    if (!inspectionId || !enabled) return;

    cancelledRef.current = false;
    startedAtRef.current = Date.now();
    const ac = new AbortController();

    // On a manual retry, keep any data we have but clear error/paused/timedOut
    // so the user sees the polling UI again.
    setState((s) => ({
      data: s.data,
      error: null,
      loading: true,
      attempts: s.attempts, // preserve total count across retries
      timedOut: false,
      paused: false,
    }));

    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    let currentInterval = intervalMs;
    let consecutiveErrors = 0;

    // When the tab is backgrounded (visibilityState === 'hidden'), throttle
    // polling to 30s to preserve mobile battery & data. When it returns to
    // visible, fire one immediate tick so the user sees fresh state.
    const HIDDEN_INTERVAL_MS = 30_000;
    const isHidden = () =>
      typeof document !== 'undefined' && document.visibilityState === 'hidden';
    const onVisibility = () => {
      if (!isHidden() && timeoutId) {
        // Tab regained focus — collapse any long pending timeout and tick now.
        clearTimeout(timeoutId);
        timeoutId = setTimeout(tick, 0);
      }
    };
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibility);
    }
    // Allow a longer transient window than the previous 5 — token refresh
    // can briefly stall a request, and 5xx blips during ML startup should
    // not look like "no internet" to the user.
    const MAX_CONSECUTIVE_ERRORS = 8;

    const tick = async () => {
      if (cancelledRef.current) return;
      try {
        const data = await getInspectionStatus(inspectionId, {
          signal: ac.signal,
        });
        if (cancelledRef.current) return;
        consecutiveErrors = 0;

        const isTerminal =
          data.status === 'completed' || data.status === 'failed';

        setState((s) => ({
          ...s,
          data,
          attempts: s.attempts + 1,
          loading: !isTerminal,
          error:
            data.status === 'failed'
              ? data.error ?? tResult('failed')
              : null,
          paused: false,
        }));

        if (isTerminal) return;

        const elapsed = Date.now() - startedAtRef.current;
        if (elapsed >= maxDurationMs) {
          setState((s) => ({ ...s, loading: false, timedOut: true }));
          return;
        }

        // Gentle exponential backoff: 1.5× per tick, capped. While the tab
        // is hidden, stretch to HIDDEN_INTERVAL_MS so background tabs don't
        // hammer the API on mobile networks.
        currentInterval = Math.min(
          Math.round(currentInterval * 1.5),
          maxIntervalMs,
        );
        const nextDelay = isHidden() ? HIDDEN_INTERVAL_MS : currentInterval;
        timeoutId = setTimeout(tick, nextDelay);
      } catch (err) {
        if (cancelledRef.current || ac.signal.aborted) return;
        const info = classifyApiError(err);

        // User cancellation: don't touch state.
        if (info.kind === 'cancelled') return;

        // Hard fatal: the request will never succeed under the current
        // session/inspection-id. Surface and stop. NOTE: 401 is handled
        // (refresh + retry) inside the axios interceptor — if it bubbles
        // up here, refresh already failed and the user is being redirected.
        const fatal =
          info.kind === 'unauthorized' ||
          info.kind === 'forbidden' ||
          info.kind === 'notFound';

        consecutiveErrors += 1;

        const message =
          info.kind === 'network'
            ? tNetwork('offline')
            : info.kind === 'timeout'
              ? tNetwork('timeout')
              : info.kind === 'unauthorized'
                ? tHttp('401')
                : info.kind === 'forbidden'
                  ? tHttp('403')
                  : info.kind === 'notFound'
                    ? tHttp('404')
                    : info.kind === 'server'
                      ? tHttp('500')
                      : info.detail ?? tNetwork('unknown');

        const exhausted = consecutiveErrors >= MAX_CONSECUTIVE_ERRORS;
        const stop = fatal || exhausted;

        setState((s) => ({
          ...s,
          attempts: s.attempts + 1,
          error: message,
          loading: !stop,
          // Mark as paused (not "timed out") when we hit the consecutive
          // error budget without a hard fatal — the inspection may still
          // be cooking server-side; UI shows a "check again" button.
          paused: exhausted && !fatal,
        }));

        if (stop) return;

        const elapsed = Date.now() - startedAtRef.current;
        if (elapsed >= maxDurationMs) {
          setState((s) => ({ ...s, loading: false, timedOut: true }));
          return;
        }

        currentInterval = Math.min(
          Math.round(currentInterval * 1.5),
          maxIntervalMs,
        );
        timeoutId = setTimeout(tick, currentInterval);
      }
    };

    void tick();

    return () => {
      cancelledRef.current = true;
      ac.abort();
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [
    inspectionId,
    intervalMs,
    maxDurationMs,
    maxIntervalMs,
    enabled,
    retryNonce,
    tResult,
    tNetwork,
    tHttp,
  ]);

  return { ...state, retry };
}
