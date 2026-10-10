import type { Profile } from './profileImport';
import type { Summary } from './reportModel';

const profiles: Profile[] = [{ profile_id: 'uk-tech-law', name: 'UK 科技法制', description: '英國科技、AI、資料治理、平台與資安政策觀測', version: 1, selected_sources: ['ICO', 'Ofcom', 'NCSC', 'UK Parliament'], topics: [{ name: 'AI', keywords: [{ phrase: 'artificial intelligence', strength: 'core' }, { phrase: 'data protection', strength: 'general' }] }], minimum_score: 3 }];
const summary = (end: string, start: string, status: string, count: number): Summary => ({ run_id: `design-${end}`, generated_at: `${end}T02:24:00Z`, status, period_start: start, period_end: end, output_file: `${start.replaceAll('-', '')}-${end.replaceAll('-', '')}_UK新聞查詢.xlsx`, profile_id: 'uk-tech-law', profile_name: 'UK 科技法制', minimum_score: 3, selected_sources: profiles[0].selected_sources, excel_date_calendar: 'gregorian', all_news_count: count, filtered_news_count: 14, parliament_count: 85, filtered_parliament_count: 1, warnings: status === 'degraded' ? ['Ofcom：部分來源未取得，已保留可用資料。'] : [], source_health: [{ source: 'ICO', critical: true, success: true, item_count: 12, duration_seconds: 2.3, warning: '' }, { source: 'Ofcom', critical: true, success: true, item_count: 8, duration_seconds: 5.1, warning: status === 'degraded' ? '使用備援資料；日期尚未核對官方發布日。' : '' }, { source: 'NCSC', critical: true, success: status !== 'degraded', item_count: status === 'degraded' ? 0 : 4, duration_seconds: 6.2, warning: status === 'degraded' ? '部分來源未取得。' : '' }], observability: { source_count: 3, source_success_rate: status === 'degraded' ? 2 / 3 : 1, source_p95_seconds: 6.2, zero_item_ratio: status === 'degraded' ? 1 / 3 : 0, alerts: [] } });
const history = [summary('2026-10-10', '2026-09-26', 'degraded', 116), summary('2026-10-03', '2026-09-19', 'complete', 108), summary('2026-09-26', '2026-09-12', 'complete', 102)];
let generation = 0;

export async function previewCommand(command: string, args: Record<string, unknown> = {}): Promise<unknown> {
  if (command === 'source_catalog') return profiles[0].selected_sources.filter(id => id !== 'UK Parliament').map(id => ({ id, name_zh: ({ ICO: '英國資訊專員辦公室', Ofcom: '英國通訊管理局', NCSC: '國家網路安全中心' } as Record<string, string>)[id], name_en: id, jurisdiction: 'UK', kind: '官方機關', homepage: 'https://www.gov.uk/', status: 'searchable', reason: '' }));
  if (command === 'profile_load_report') return { profiles, warning: '', recovery_path: null };
  if (command === 'list_profiles') return profiles;
  if (command === 'recent_runs') return [...history];
  if (command === 'suggested_output') return `${String(args.since).replaceAll('-', '')}-${String(args.until).replaceAll('-', '')}_UK新聞查詢.xlsx`;
  if (command === 'save_profile') { const profile = args.profile as Profile; const index = profiles.findIndex(item => item.profile_id === profile.profile_id); if (index < 0) profiles.push(profile); else profiles[index] = profile; return 'design-preview'; }
  if (command === 'delete_profile') { const index = profiles.findIndex(item => item.profile_id === args.profileId); if (index > 0) profiles.splice(index, 1); return index > 0; }
  if (command === 'cancel_run') { generation += 1; return true; }
  if (command === 'run_scraper' || command === 'retry_failed') {
    const token = ++generation;
    const request = args.request as Record<string, unknown>;
    const run = (command === 'retry_failed' ? request.run : request) as Record<string, unknown>;
    for (const [index, kind] of ['fetching', 'filtering', 'translating', 'exporting', 'completed'].entries()) {
      await new Promise(resolve => setTimeout(resolve, 350));
      if (token !== generation) throw new Error('設計預覽執行已取消');
      window.dispatchEvent(new CustomEvent('scraper-progress', { detail: { kind, completed: index, total: 4, source: '', message: '正在模擬執行流程（不抓取資料）' } }));
    }
    const item = summary(String(run.until), String(run.since), 'complete', 116);
    item.output_file = String(run.output);
    item.profile_id = String((run.profile as Profile)?.profile_id ?? 'uk-tech-law');
    item.profile_name = String((run.profile as Profile)?.name ?? 'UK 科技法制');
    history.unshift(item);
    return { workbook_path: item.output_file, summary_path: item.output_file.replace(/\.xlsx$/i, '.run.json'), summary: item, news: [{ published_at: `${run.until}T00:00:00Z`, unit_category: 'ICO', title: 'AI and data protection — design example', link: 'https://ico.org.uk/', content_type: 'guidance', matched_topics: ['AI'], matched_keywords: ['AI'], title_matched_keywords: ['AI'], summary_matched_keywords: [], relevance_score: 6 }], parliament: [] };
  }
  throw new Error(`設計預覽不支援此操作：${command}`);
}
