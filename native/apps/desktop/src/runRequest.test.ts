import { describe, expect, it } from 'vitest';
import { buildRunRequest, workerChoices } from './runRequest';

const base = {
  since: '2026-09-10',
  until: '2026-09-24',
  output: '/tmp/uk-news.xlsx',
  profile: { profile_id: 'uk-tech-law', name: 'UK 科技法制' },
  calendar: 'gregorian',
  selectedSources: ['BIST', 'UK Parliament'],
  minimumScore: 3,
};

describe('desktop run request', () => {
  it('offers the same 1–16 source concurrency range as the Python desktop UI', () => {
    expect(workerChoices).toEqual(Array.from({ length: 16 }, (_, index) => index + 1));
  });

  it('passes the chosen worker count to ordinary runs and source retries', () => {
    expect(buildRunRequest({ ...base, workers: 6 }).workers).toBe(6);
    const retry = buildRunRequest({ ...base, workers: 12, output: '/tmp/retry.xlsx' });
    expect(retry).toMatchObject({ workers: 12, output: '/tmp/retry.xlsx' });
    expect(retry.profile).toMatchObject({ selected_sources: ['BIST', 'UK Parliament'] });
  });

  it('rejects invalid worker counts before invoking the scraper', () => {
    for (const workers of [0, 17, 2.5, Number.NaN]) {
      expect(() => buildRunRequest({ ...base, workers })).toThrow('併發抓取數');
    }
  });
});
