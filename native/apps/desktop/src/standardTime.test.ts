import { describe, it, expect } from 'vitest';
import { clockDate, headerTime, timeSourceLabel } from './standardTime';
import { defaultPeriod } from './period';
describe('national standard time', () => {
  it('uses a monotonic anchor across the Taipei midnight boundary', () => {
    const snapshot = { state: { source: 'ntp', server: 'tock.stdtime.gov.tw', utc: '2026-10-11T15:59:59Z' }, anchoredAt: 100 };
    expect(defaultPeriod(clockDate(snapshot, 2100)).until).toBe('2026-10-12');
    expect(clockDate(snapshot, 0).toISOString()).toBe('2026-10-11T15:59:59.000Z');
  });
  it('distinguishes pending calibration, success and system fallback', () => {
    expect(timeSourceLabel()).toContain('正在連接');
    expect(timeSourceLabel({ source: 'ntp', server: 'time.stdtime.gov.tw', utc: '' })).toContain('國家標準時間');
    expect(timeSourceLabel({ source: 'system', utc: '', warning: 'UDP 123 無法連線' })).toContain('UDP 123');
  });
  it('labels the calibrated date as national standard time and updates across midnight', () => {
    const snapshot = { state: { source: 'ntp', utc: '2026-10-11T15:59:59Z' }, anchoredAt: 100 };
    expect(headerTime(snapshot, 100)).toEqual({ date: '2026-10-11', label: '國家標準時間' });
    expect(headerTime(snapshot, 2100)).toEqual({ date: '2026-10-12', label: '國家標準時間' });
    expect(headerTime({ ...snapshot, state: { ...snapshot.state, source: 'system' } }, 2100).label).toBe('本機時間');
    expect(headerTime(undefined, 100).label).toBe('校時中');
  });
});
