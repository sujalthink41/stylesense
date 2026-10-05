import type { Action, GenUIComponent } from './types';

/**
 * The server decides where "back" goes (ADR 0011): the hardware back button sends the Back the
 * screen itself offers, if any. No offer means the first screen, so the app leaves the session.
 */
export function backAction(components: GenUIComponent[]): Action | null {
  for (const c of components) {
    const options =
      c.type === 'suggestion_bar' ? c.props.suggestions : c.type === 'empty_state' ? (c.props.recovery ?? []) : [];
    const back = options.find((s) => (s.action as Action).type === 'back');
    if (back) return back.action as Action;
  }
  return null;
}
