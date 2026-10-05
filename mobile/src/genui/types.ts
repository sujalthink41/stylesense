/** Friendly aliases over the generated contract (types.gen.ts). */
import type { Action, UiEnvelope } from './types.gen';

export type { Action, UiEnvelope };
export type GenUIComponent = UiEnvelope['components'][number];
export type ComponentType = NonNullable<GenUIComponent['type']>;

/** What a rendered component may do: send an action for the next turn, or record a swipe. */
export interface GenUIContext {
  sessionId: string;
  turnId: number;
  /** True while a turn is in flight: controls disable instead of queueing taps. */
  busy: boolean;
  dispatch(action: Action): void;
}
