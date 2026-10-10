export type SourceHealth = { source: string; critical: boolean; success: boolean; item_count: number; duration_seconds: number; warning: string; candidate_count?: number; endpoints?: { url: string; status_code: number; fetched_at: string }[] };
export type Observability = { source_count: number; source_success_rate: number; source_p95_seconds: number; zero_item_ratio: number; alerts: string[] };
export type Summary = { run_id: string; generated_at?: string; status: string; period_start: string; period_end: string; output_file: string; profile_id: string; profile_name?: string; minimum_score: number; selected_sources?: string[]; excel_date_calendar?: string; all_news_count: number; filtered_news_count: number; parliament_count: number; filtered_parliament_count: number; source_health: SourceHealth[]; warnings: string[]; observability?: Observability };

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
