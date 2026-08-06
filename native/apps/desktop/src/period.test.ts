import { describe, expect, it } from 'vitest';
import { defaultPeriod } from './period';

describe('defaultPeriod', () => {
  it('uses an inclusive fourteen-day calendar range', () => {
    expect(defaultPeriod(new Date('2026-08-06T12:00:00Z'))).toEqual({
      since: '2026-07-24',
      until: '2026-08-06',
    });
  });
});
