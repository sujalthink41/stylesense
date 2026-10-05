import { create } from 'zustand';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { ActionResult, SessionEntry, SessionView } from '@/api/types';
import type { Action } from '@/genui/types';

export type Phase = 'idle' | 'starting' | 'acting';

export interface StylistState {
  session: SessionView | null;
  phase: Phase;
  error: ApiError | null;
  start(entry: SessionEntry, value?: string | null): Promise<string | null>;
  open(sessionId: string): Promise<void>;
  act(action: Action): Promise<void>;
  clearError(): void;
}

const BUSY_RETRY_MS = 1_200;

/**
 * Client side of the turn engine (ADR 0011): every action names the turn it acts on. A stale
 * turn (double tap, second device) just means "you're behind": fetch the current screen.
 */
export function createStylistStore(api: ApiClient, sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))) {
  return create<StylistState>()((set, get) => {
    const snapshot = async (sessionId: string) => {
      const session = await api.get<SessionView>(`/v1/stylist/sessions/${sessionId}`);
      set({ session });
    };
    return {
      session: null,
      phase: 'idle',
      error: null,
      clearError: () => set({ error: null }),

      async start(entry, value) {
        set({ phase: 'starting', error: null });
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
        set({ phase: 'acting', error: null });
        const send = () =>
          api.post<ActionResult>(`/v1/stylist/sessions/${current.session_id}/actions`, {
            turn_id: current.turn_id,
            action,
          });
        try {
          let result: ActionResult;
          try {
            result = await send();
          } catch (error) {
            if (error instanceof ApiError && error.code === 'session_busy') {
              await sleep(BUSY_RETRY_MS);
              result = await send();
            } else throw error;
          }
          if (result.ui) {
            set({ session: { ...current, turn_id: result.turn_id, ui: result.ui } });
          }
          if (result.error) set({ error: asApiError(result.error) });
        } catch (error) {
          const e = asApiError(error);
          if (e.code === 'stale_turn' || e.code === 'session_busy') {
            await snapshot(current.session_id).catch(() => undefined); // catch up silently
          } else {
            set({ error: e });
          }
        } finally {
          set({ phase: 'idle' });
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
