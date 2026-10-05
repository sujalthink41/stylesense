import { createTimers } from '../perf';

describe('timers', () => {
  it('measures from start to the first end only', () => {
    let now = 1_000;
    const report = jest.fn();
    const timers = createTimers(() => now, report);

    timers.start('first_products');
    now = 3_400;
    expect(timers.end('first_products')).toBe(2_400);
    now = 9_000;
    expect(timers.end('first_products')).toBeNull(); // a refill isn't "first" any more

    expect(report).toHaveBeenCalledTimes(1);
    expect(report).toHaveBeenCalledWith('first_products', 2_400);
  });

  it('restarting resets the clock; ending an unknown timer is a no-op', () => {
    let now = 0;
    const timers = createTimers(() => now, jest.fn());

    timers.start('t');
    now = 500;
    timers.start('t');
    now = 800;

    expect(timers.end('t')).toBe(300);
    expect(timers.end('never')).toBeNull();
  });
});
