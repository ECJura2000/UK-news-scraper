export type SourceHealth = { source: string; critical: boolean; success: boolean; item_count: number; duration_seconds: number; warning: string; candidate_count?: number; endpoints?: { url: string; status_code: number; fetched_at: string }[] };
export type Observability = { source_count: number; source_success_rate: number; source_p95_seconds: number; zero_item_ratio: number; alerts: string[] };
export type Performance = { schema_version: number; runtime: string; runtime_version: string; run_kind: string; workers: number; total_wall_seconds: number; total_endpoint?: string; translation_cache_hits: number; translation_cache_misses: number; stages: Record<string, number | null>; http: Record<string, { attempted_count: number; retry_count: number; rate_limited_count: number }> };
export type Summary = { time_sync?: { source?: string; server?: string; offset_seconds?: number | null; warning?: string }; performance?: Performance; profile_hash?: string; run_id: string; generated_at?: string; status: string; period_start: string; period_end: string; output_file: string; profile_id: string; profile_name?: string; minimum_score: number; selected_sources?: string[]; excel_date_calendar?: string; all_news_count: number; filtered_news_count: number; parliament_count: number; filtered_parliament_count: number; source_health: SourceHealth[]; warnings: string[]; observability?: Observability };

export const reportKey = (summary: Summary) => `${summary.run_id}\n${summary.output_file}`;
export const needsRetry = (summary: Summary) => summary.source_health.some(source => !source.success || Boolean(source.warning));
export const reportStatus = (summary: Summary) => summary.status === 'complete' ? '已產生・完整' : summary.status === 'degraded' ? '已產生・來源需注意' : '執行失敗';
export function reportList(history: Summary[], latest?: Summary): Summary[] {
  const values = new Map<string, Summary>();
  for (const item of history) values.set(reportKey(item), item);
  if (latest) values.set(reportKey(latest), latest);
  return [...values.values()].sort((a, b) => (b.generated_at ?? '').localeCompare(a.generated_at ?? '') || b.period_end.localeCompare(a.period_end));
}
export function selectReport(reports: Summary[], key: string): Summary | undefined {
  return reports.find(item => reportKey(item) === key) ?? reports[0];
}
export function reportTimestamp(value?: string) {
  if (!value || Number.isNaN(Date.parse(value))) return '未記錄';
  return new Intl.DateTimeFormat('zh-TW', { timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
}

export type HealthAdvice = { label: string; action: string };
export function healthAdvice(source: SourceHealth): HealthAdvice[] {
  const warning = source.warning;
  const result: HealthAdvice[] = [];
  if (!source.success) result.push({ label: '取得失敗', action: /403|429|challenge|Forbidden/i.test(warning) ? '網站限制存取；稍後重試，持續發生時檢查官方端點。' : '可先重試；持續失敗時檢查官方端點與連線。' });
  if (/解析為零|未解析到|解析失敗|欄位不完整|頁面格式/.test(warning) || (source.candidate_count ?? 0) > 0 && source.item_count === 0) result.push({ label: '解析需檢查', action: '檢查原始回應與解析器；單純重試可能無法改善。' });
  if (/最舊|期間可能不完整|歷史|涵蓋/.test(warning)) result.push({ label: '期間涵蓋不足', action: '改用可分頁的官方管道或縮短查詢期間；重試同一列表通常無法補齊歷史資料。' });
  if (/備援|fallback/i.test(warning)) result.push({ label: '使用備援', action: '開啟官方原文核對發布日期；官方管道恢復後再重試。' });
  if (/最新資料已超過|筆數異常|健康門檻/.test(warning)) result.push({ label: '發布頻率需核對', action: '核對官方近期發布情況；來源可能低頻發布，也可能漏抓。' });
  if (!result.length && warning) result.push({ label: '需注意', action: '依下方原始警告檢查來源；無法判定時保留現有資料再查核。' });
  if (!result.length) result.push(source.item_count === 0
    ? { label: '期間內未取得資料', action: '零筆不等於失敗；若預期有文章，請核對官方頁面。' }
    : { label: '正常', action: '已取得資料。' });
  return result;
}
export function measuredPerformance(summary: Summary): Performance | undefined {
  const p = summary.performance;
  return p?.schema_version === 1 && Number.isFinite(p.total_wall_seconds) && p.total_wall_seconds > 0 && Boolean(p.runtime_version) ? p : undefined;
}
export const stageLabels: Record<string, string> = {
  collection_wall_seconds: '來源採集', dedupe_work_seconds: '去除重複資料', relevance_seconds: '主題篩選',
  translation_seconds: '標題翻譯', excel_write_seconds: 'Excel 匯出', json_write_seconds: '資料保存',
};
export function durationText(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? `${value.toFixed(2)} 秒` : '未記錄';
}
