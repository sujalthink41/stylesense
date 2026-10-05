import { backAction } from '../navigation';
import type { GenUIComponent } from '../types';

const bar = (...actions: object[]) =>
  ({
    id: 'next',
    type: 'suggestion_bar',
    props: { suggestions: actions.map((action, i) => ({ id: `s${i}`, label: 'x', action })) },
  }) as unknown as GenUIComponent;

describe('system back inside a session', () => {
  it("uses the server's own Back suggestion", () => {
    expect(backAction([bar({ type: 'restart' }, { type: 'back' })])).toEqual({ type: 'back' });
  });

  it('finds Back in an empty state recovery too', () => {
    const empty = { id: 'e', type: 'empty_state', props: { title: 'No luck', recovery: [{ id: 'b', label: 'Back', action: { type: 'back' } }] } };

    expect(backAction([empty as unknown as GenUIComponent])).toEqual({ type: 'back' });
  });

  it('is null when the screen offers no way back (first question): the app leaves instead', () => {
    expect(backAction([bar({ type: 'restart' })])).toBeNull();
    expect(backAction([])).toBeNull();
  });
});
