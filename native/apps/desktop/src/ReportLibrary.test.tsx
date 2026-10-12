import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ReportLibrary } from './ReportLibrary';
import type { Summary } from './reportModel';

const selected: Summary = { run_id: 'test', output_file: 'test.xlsx', status: 'degraded', period_start: '2026-10-01', period_end: '2026-10-07', profile_id: 'test', minimum_score: 3, all_news_count: 5, filtered_news_count: 2, parliament_count: 1, filtered_parliament_count: 1, warnings: [], source_health: [{ source: 'ICO', critical: true, success: true, item_count: 0, duration_seconds: 1, warning: '' }] };
function render(summary: Summary) {
  return renderToStaticMarkup(<ReportLibrary reports={[summary]} selected={summary} running={false} showAllHealth={true} onSelect={() => {}} onCreate={() => {}} onOpen={() => {}} onRetry={() => {}} onToggleHealth={() => {}} />);
}
describe('report diagnostic presentation', () => {
  it('shows ordinary zero-result advice and distinguishes older reports', () => {
    const html = render(selected);
    expect(html).toContain('零筆不等於失敗');
    expect(html).not.toContain('順利取得資料');
    expect(html).toContain('沒有可用的實測效能紀錄');
  });
  it('shows measured stages, null timings, network costs and retry boundaries', () => {
    const html = render({ ...selected, performance: { schema_version: 1, runtime: 'rust', runtime_version: '2.3.6', run_kind: 'retry', workers: 8, total_wall_seconds: 5, translation_cache_hits: 2, translation_cache_misses: 1, stages: { translation_seconds: 1, json_write_seconds: null }, http: { list: { attempted_count: 4, retry_count: 1, rate_limited_count: 2 } } } });
    expect(html).toContain('本次重試');
    expect(html).toContain('5.00 秒');
    expect(html).toContain('1.00 秒');
    expect(html).toContain('未記錄');
    expect(html).toContain('來源列表');
    expect(html).toContain('各階段可能重疊，不能相加');
  });
  it('shows measured time correction and preserves unknown legacy calibration', () => {
    const unknown = render({ ...selected, time_sync: {} });
    expect(unknown).toContain('未記錄校時資訊');
    expect(unknown).toContain('未記錄校正差值');
    expect(unknown).not.toContain('校正差值 0.00');
    const calibrated = render({ ...selected, time_sync: { source: 'ntp', server: 'tock.stdtime.gov.tw', offset_seconds: -0.002 } });
    expect(calibrated).toContain('國家標準時間 · tock.stdtime.gov.tw');
    expect(calibrated).toContain('-2.00 毫秒');
  });
});
