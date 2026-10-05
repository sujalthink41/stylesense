import * as Sentry from '@sentry/react-native';

type Report = (name: string, ms: number) => void;

/** Named one-shot timers: start, then the first end reports the elapsed time. */
export function createTimers(now: () => number, report: Report) {
  const started = new Map<string, number>();
  return {
    start(name: string) {
      started.set(name, now());
    },
    end(name: string): number | null {
      const at = started.get(name);
      if (at === undefined) return null;
      started.delete(name);
      const ms = now() - at;
      report(name, ms);
      return ms;
    },
  };
}

const report: Report = (name, ms) => {
  if (__DEV__) console.log(`[perf] ${name} ${ms} ms`); // visible in the Metro terminal
  Sentry.addBreadcrumb({ category: 'perf', message: name, data: { ms }, level: 'info' });
};

/**
 * App-wide timers. `tap_to_products`: the last tap (start or answer) → its deck on screen.
 * Restarted on every tap, so time spent reading a question never counts (CP16 exit: < 5 s).
 */
export const timers = createTimers(() => Date.now(), report);
