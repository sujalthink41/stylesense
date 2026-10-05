/** Compares "major.minor.patch" versions; anything unparsable counts as 0.0.0. */
export function compareVersions(a: string, b: string): number {
  const parse = (v: string) => {
    const m = /^(\d+)\.(\d+)\.(\d+)/.exec(v.trim());
    return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : [0, 0, 0];
  };
  const [x, y] = [parse(a), parse(b)];
  for (let i = 0; i < 3; i++) {
    const d = (x[i] ?? 0) - (y[i] ?? 0);
    if (d !== 0) return d < 0 ? -1 : 1;
  }
  return 0;
}

export type UpdateState = 'ok' | 'recommended' | 'required';

/** Below the minimum supported version the app must update; below latest it may. */
export function updateState(current: string, minSupported: string, latest: string): UpdateState {
  if (compareVersions(current, minSupported) < 0) return 'required';
  if (compareVersions(current, latest) < 0) return 'recommended';
  return 'ok';
}
