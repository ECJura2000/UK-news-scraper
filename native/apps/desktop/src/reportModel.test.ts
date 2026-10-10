import { describe, expect, it } from 'vitest';
import { needsRetry, reportKey, reportList, reportStatus, reportTimestamp, selectReport, type Summary } from './reportModel';

const report = (run_id: string, output_file = 'report.xlsx'): Summary => ({ run_id, output_file, generated_at: '2026-10-10T02:24:00Z', status: 'complete', period_start: '2026-09-26', period_end: '2026-10-10', profile_id: 'uk-tech-law', minimum_score: 3, all_news_count: 2, filtered_news_count: 1, parliament_count: 3, filtered_parliament_count: 0, source_health: [], warnings: [] });
describe('report library boundaries', () => {
  it('replaces a retry of the same report without duplicating it or mixing another path', () => {
    const previous = report('same'); const other = report('same', 'other.xlsx');
    const latest = { ...previous, filtered_news_count: 2 };
    const list = reportList([previous, other], latest);
    expect(list).toHaveLength(2);
    expect(selectReport(list, reportKey(latest))).toBe(latest);
    expect(selectReport(list, reportKey(other))).toBe(other);
  });
  it('uses a present report after a selected report disappears and handles an empty folder', () => {
    expect(selectReport([report('a')], 'missing')?.run_id).toBe('a');
    expect(selectReport([], 'missing')).toBeUndefined();
  });
  it('keeps logical counts and distinguishes source warnings from legitimate zero records', () => {
    const empty = { ...report('empty'), source_health: [{ source: 'ICO', critical: true, success: true, item_count: 0, duration_seconds: 1, warning: '' }] };
    expect(needsRetry(empty)).toBe(false);
    expect(needsRetry({ ...empty, source_health: [{ ...empty.source_health[0], warning: 'fallback' }] })).toBe(true);
    expect(needsRetry({ ...empty, source_health: [{ ...empty.source_health[0], success: false }] })).toBe(true);
    expect(reportStatus({ ...empty, status: 'degraded' })).toBe('已產生・來源需注意');
    expect(empty.all_news_count).toBe(2);
  });
  it('displays run times in Taipei and accepts older summaries without timestamps', () => {
    expect(reportTimestamp('2026-10-09T18:24:00Z')).toContain('2026/10/10');
    expect(reportTimestamp('2026-10-09T18:24:00Z')).toContain('02:24');
    expect(reportTimestamp()).toBe('未記錄');
    expect(reportTimestamp('invalid')).toBe('未記錄');
  });
});
