import { describe, expect, it } from 'vitest';
import { defaultPeriod } from './period';

describe('defaultPeriod', () => {
  it('uses the same fourteen-day lookback as the weekly CLI', () => {
    expect(defaultPeriod(new Date('2026-08-06T12:00:00Z'))).toEqual({
      since: '2026-07-23',
      until: '2026-08-06',
    });
  });
  it('uses the Taiwan calendar day rather than the UTC day', () => {
    expect(defaultPeriod(new Date('2026-08-05T17:00:00Z'), 7)).toEqual({ since: '2026-07-30', until: '2026-08-06' });
  });
});
