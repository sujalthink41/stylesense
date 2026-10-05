import { compareVersions, updateState } from '../version';

describe('versions', () => {
  it('compares numerically, not as strings', () => {
    expect(compareVersions('0.10.0', '0.9.0')).toBe(1);
    expect(compareVersions('1.0.0', '1.0.0')).toBe(0);
    expect(compareVersions('1.2.3', '1.2.4')).toBe(-1);
  });

  it('treats garbage as 0.0.0 rather than crashing', () => {
    expect(compareVersions('nonsense', '0.0.1')).toBe(-1);
  });

  it('requires an update below the minimum and recommends one below latest', () => {
    expect(updateState('0.1.0', '0.2.0', '0.3.0')).toBe('required');
    expect(updateState('0.2.0', '0.2.0', '0.3.0')).toBe('recommended');
    expect(updateState('0.3.0', '0.2.0', '0.3.0')).toBe('ok');
  });
});
