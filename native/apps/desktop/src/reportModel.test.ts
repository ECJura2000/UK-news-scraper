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

import { healthAdvice, measuredPerformance, durationText } from './reportModel';
describe('diagnostic advice and measurements', () => {
  const source = { source: 'ICO', critical: true, success: true, item_count: 0, duration_seconds: 1, warning: '' };
  it('does not invent unpublished news or recommend retrying ordinary zero results', () => {
    expect(healthAdvice(source)[0].label).toBe('期間內未取得資料');
    expect(healthAdvice(source)[0].action).toContain('零筆不等於失敗');
    expect(healthAdvice({ ...source, candidate_count: 2 })[0].label).toBe('解析需檢查');
  });
  it('retains distinct actions for combined failures, parser changes, coverage and fallback', () => {
    const advice = healthAdvice({ ...source, success: false, warning: '403；解析為零筆；官方 RSS 最舊資料晚於查詢起日，期間可能不完整；使用 Google News 備援' });
    expect(advice.map(item => item.label)).toEqual(['取得失敗', '解析需檢查', '期間涵蓋不足', '使用備援']);
    expect(advice[0].action).toContain('網站限制存取');
    expect(advice[2].action).toContain('通常無法補齊');
    expect(healthAdvice({ ...source, warning: '最新資料已超過 30 天' })[0].label).toBe('發布頻率需核對');
    expect(healthAdvice({ ...source, warning: 'new unknown warning' })[0].label).toBe('需注意');
  });
  it('keeps old defaults and unavailable timings distinct from measured zero-duration stages', () => {
    expect(measuredPerformance(report('old'))).toBeUndefined();
    expect(durationText(null)).toBe('未記錄');
    expect(durationText(NaN)).toBe('未記錄');
    expect(durationText(0)).toBe('0.00 秒');
    const performance = { schema_version: 1, runtime: 'python', runtime_version: '2.3.6', run_kind: 'full', workers: 8, total_wall_seconds: 10, translation_cache_hits: 0, translation_cache_misses: 0, stages: {}, http: {} };
    expect(measuredPerformance({ ...report('new'), performance })).toBe(performance);
    expect(measuredPerformance({ ...report('legacy'), performance: { ...performance, total_wall_seconds: 0 } })).toBeUndefined();
  });
});
