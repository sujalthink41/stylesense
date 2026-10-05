import { create } from 'zustand';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { SSEEvent } from '@/api/sse';
import { timers } from '@/lib/perf';
import type { ActionResult, SessionEntry, SessionView } from '@/api/types';
import type { Action, GenUIComponent } from '@/genui/types';

type Screen = SessionView['ui'];

export type Phase = 'idle' | 'starting' | 'acting';

export interface StylistState {
  session: SessionView | null;
  phase: Phase;
  error: ApiError | null;
  /** Skeletons the server sent for the turn in flight (shape-aware loading). */
  loading: GenUIComponent[] | null;
  start(entry: SessionEntry, value?: string | null): Promise<string | null>;
  open(sessionId: string): Promise<void>;
  act(action: Action): Promise<void>;
  clearError(): void;
}

const BUSY_RETRY_MS = 1_200;
const RESUME_POLL_MS = 1_000;
const RESUME_ATTEMPTS = 8;

/**
 * Client side of the turn engine (ADR 0011): every action names the turn it acts on. A stale
 * turn (double tap, second device) just means "you're behind": fetch the current screen.
 */
export function createStylistStore(api: ApiClient, sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))) {
  return create<StylistState>()((set, get) => {
    const snapshot = async (sessionId: string) => {
      const session = await api.get<SessionView>(`/v1/stylist/sessions/${sessionId}`);
      set({ session });
      return session;
    };
    // The turn keeps running server-side after a dropped stream: wait for it, never resend.
    const resume = async (sessionId: string) => {
      for (let i = 0; i < RESUME_ATTEMPTS; i++) {
        const session = await snapshot(sessionId);
        if (session.status !== 'busy') return;
        await sleep(RESUME_POLL_MS);
      }
      throw new ApiError({ status: 0, code: 'stream_lost', title: 'Connection lost' });
    };
    return {
      session: null,
      phase: 'idle',
      error: null,
      loading: null,
      clearError: () => set({ error: null }),

      async start(entry, value) {
        set({ phase: 'starting', error: null });
        timers.start('first_products');
        try {
          const session = await api.post<SessionView>('/v1/stylist/sessions', {
            entry,
            value: value?.trim() ? value.trim() : null,
          });
          set({ session, phase: 'idle' });
          return session.session_id;
        } catch (error) {
          set({ phase: 'idle', error: asApiError(error) });
          return null;
        }
      },

      async open(sessionId) {
        if (get().session?.session_id === sessionId) return;
        set({ phase: 'starting', error: null });
        try {
          await snapshot(sessionId);
        } catch (error) {
          set({ error: asApiError(error) });
        } finally {
          set({ phase: 'idle' });
        }
      },

      async act(action) {
        const current = get().session;
        if (!current || get().phase !== 'idle') return; // one turn at a time
        set({ phase: 'acting', error: null, loading: null });
        const adopt = (ui: Screen) => set({ session: { ...current, status: 'active', turn_id: ui.turn_id, ui }, loading: null });
        const onEvent = (e: SSEEvent) => {
          const data = parseJson(e.data);
          if (!data) return;
          if (e.event === 'ui.loading') set({ loading: (data.components as GenUIComponent[]) ?? null });
          else if (e.event === 'ui.render') adopt(data.envelope as Screen);
          else if (e.event === 'error') set({ error: asApiError(data.problem) });
        };
        const send = () =>
          api.events<ActionResult>(`/v1/stylist/sessions/${current.session_id}/actions`, { turn_id: current.turn_id, action }, onEvent);
        try {
          let outcome: Awaited<ReturnType<typeof send>>;
          try {
            outcome = await send();
          } catch (error) {
            if (error instanceof ApiError && error.code === 'session_busy') {
              await sleep(BUSY_RETRY_MS);
              outcome = await send();
            } else throw error;
          }
          if (!outcome.streamed) {
            if (outcome.body.ui) adopt(outcome.body.ui);
            if (outcome.body.error) set({ error: asApiError(outcome.body.error) });
          }
        } catch (error) {
          const e = asApiError(error);
          if (e.code === 'stream_lost') {
            await resume(current.session_id).catch((err: unknown) => set({ error: asApiError(err) }));
          } else if (e.code === 'stale_turn' || e.code === 'session_busy') {
            await snapshot(current.session_id).catch(() => undefined); // catch up silently
          } else {
            set({ error: e });
          }
        } finally {
          set({ phase: 'idle', loading: null });
        }
      },
    };
  });
}

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (error && typeof error === 'object' && 'code' in error) {
    const p = error as { status?: number; code?: string; title?: string; detail?: string };
    return new ApiError({ status: p.status ?? 500, code: p.code ?? 'turn_failed', title: p.title ?? 'Something went wrong', detail: p.detail });
  }
  return new ApiError({ status: 0, code: 'unknown', title: 'Something went wrong' });
}

function parseJson(text: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(text);
    return value && typeof value === 'object' ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}
