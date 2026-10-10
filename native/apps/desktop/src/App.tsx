import React, { useEffect, useMemo, useRef, useState } from 'react';
import { invoke, listen, save, openPath, openUrl, designPreview } from './desktopBridge';
import { ClockCounterClockwise, MagnifyingGlass, SlidersHorizontal, Question, ArrowLeft, Plus } from '@phosphor-icons/react';
import clockTower from './assets/clock-tower.png';
import { ReportLibrary } from './ReportLibrary';
import { reportKey, reportList, selectReport, type Summary } from './reportModel';
import { defaultPeriod } from './period';
import { parseProfileJson, type Profile } from './profileImport';
import { buildRunRequest, workerChoices } from './runRequest';
import './style.css';

type CatalogEntry = { id: string; name_zh: string; name_en: string; jurisdiction: string; kind: string; homepage: string; status: string; reason: string };
type Agency = { short_name: string; name_zh: string; name_en: string; topics: string[]; homepage: string; jurisdiction: string; kind: string; searchable: boolean; reason: string };
type ProfileReport = { profiles: Profile[]; warning: string; recovery_path: string | null };
type News = { published_at: string; unit_category: string | null; title: string; link: string; content_type: string; matched_topics: string[]; matched_keywords: string[]; title_matched_keywords: string[]; summary_matched_keywords: string[]; relevance_score: number };
type Parliament = { published_at: string; publisher: string; title: string; webpage_url: string; matched_topics: string[]; matched_keywords: string[]; title_matched_keywords: string[]; summary_matched_keywords: string[]; relevance_score: number };
type Result = { workbook_path: string; summary_path: string; summary: Summary; news: News[]; parliament: Parliament[] };
type PreviewRow = { date: string; source: string; type: string; title: string; url: string; topics: string[]; score: number; reason: string };
type RunProgress = { kind: string; completed: number; total: number; source: string; message: string };

const outputDirectory = (path: string) => { const value = path.replace(/[\\/][^\\/]+$/, ''); return value === path ? '.' : value };

function App() {
  const profileImportRef = useRef<HTMLInputElement>(null);
  const initial = defaultPeriod(new Date());
  const [sources, setSources] = useState<Agency[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [since, setSince] = useState(initial.since);
  const [until, setUntil] = useState(initial.until);
  const [output, setOutput] = useState('');
  const [customOutput, setCustomOutput] = useState(false);
  const [calendar, setCalendar] = useState('gregorian');
  const [minimumScore, setMinimumScore] = useState(3);
  const [workers, setWorkers] = useState(6);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [history, setHistory] = useState<Summary[]>([]);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [sourceLimit, setSourceLimit] = useState(60);
  const [jurisdiction, setJurisdiction] = useState('all');
  const [resultQuery, setResultQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [scoreFilter, setScoreFilter] = useState(0);
  const [sortKey, setSortKey] = useState<'date' | 'score' | 'source'>('date');
  const [onlyFiltered, setOnlyFiltered] = useState(true);
  const [progress, setProgress] = useState<RunProgress | null>(null);
  const [showHealth, setShowHealth] = useState(false);
  const [page, setPage] = useState<'history' | 'query' | 'settings' | 'results'>('history');
  const [selectedReportKey, setSelectedReportKey] = useState('');
  const [helpOpen, setHelpOpen] = useState(false);
  const [previewNotice, setPreviewNotice] = useState('');
  const reports = useMemo(() => reportList(history, result && outputDirectory(result.summary.output_file) === outputDirectory(output) ? result.summary : undefined), [history, result, output]);
  const activeReport = selectReport(reports, selectedReportKey);
  const selectLibraryReport = (summary: Summary) => { setSelectedReportKey(reportKey(summary)); setShowHealth(false) };

  function selectProfile(value: Profile) { setProfile(value); setSelected(new Set(value.selected_sources)); setMinimumScore(value.minimum_score) }
  async function refreshProfiles(preferred?: string) { const values = await invoke<Profile[]>('list_profiles'); setProfiles(values); const next = values.find(item => item.profile_id === preferred) ?? values[0]; if (next) selectProfile(next) }

  useEffect(() => { Promise.all([invoke<CatalogEntry[]>('source_catalog'), invoke<ProfileReport>('profile_load_report')]).then(([catalog, report]) => { setSources([...catalog.map(item => ({ short_name: item.id, name_zh: item.name_zh || item.name_en, name_en: item.name_en, topics: [item.kind], homepage: item.homepage, jurisdiction: item.jurisdiction, kind: item.kind, searchable: item.status === 'searchable', reason: item.reason })), { short_name: 'UK Parliament', name_zh: '英國國會研究資料', name_en: 'UK Parliament Research Briefings', topics: ['Commons Library', 'Lords Library', 'POST'], homepage: 'https://www.parliament.uk/', jurisdiction: 'UK', kind: '國會', searchable: true, reason: '' }]); setProfiles(report.profiles); if (report.profiles[0]) selectProfile(report.profiles[0]); if (report.warning) setError(report.warning) }).catch(reason => setError(String(reason))) }, []);
  useEffect(() => { let active = true; let unlisten: (() => void) | undefined; listen<RunProgress>('scraper-progress', event => { if (active) setProgress(event.payload) }).then(stop => { if (active) unlisten = stop; else stop() }).catch(reason => { if (active) setError(String(reason)) }); return () => { active = false; unlisten?.() } }, []);
  useEffect(() => { const notify = (event: Event) => setPreviewNotice((event as CustomEvent<string>).detail); window.addEventListener('preview-notice', notify); return () => window.removeEventListener('preview-notice', notify) }, []);
  useEffect(() => { let active = true; if (!customOutput && profile) invoke<string>('suggested_output', { since, until, profileId: profile.profile_id }).then(value => { if (active) setOutput(value) }).catch(reason => { if (active) setError(String(reason)) }); return () => { active = false } }, [since, until, profile?.profile_id, customOutput]);
  useEffect(() => { let active = true; invoke<Summary[]>('recent_runs', { outputDir: outputDirectory(output) }).then(value => { if (active) setHistory(value) }).catch(() => { if (active) setHistory([]) }); return () => { active = false } }, [output, result]);
  const matchingSources = useMemo(() => sources.filter(source => (jurisdiction === 'all' || source.jurisdiction === jurisdiction) && `${source.short_name}${source.name_zh}${source.name_en}${source.kind}`.toLowerCase().includes(query.toLowerCase())).sort((a, b) => Number(selected.has(b.short_name)) - Number(selected.has(a.short_name)) || a.name_en.localeCompare(b.name_en)), [sources, query, jurisdiction, selected]);
  const shown = matchingSources.slice(0, sourceLimit);
  const rows = useMemo(() => {
    if (!result) return [];
    const values: PreviewRow[] = [
      ...result.news.map(item => ({ date: item.published_at.slice(0, 10), source: item.unit_category ?? '', type: item.content_type, title: item.title, url: item.link, topics: item.matched_topics, score: item.relevance_score, reason: [...item.title_matched_keywords.map(word => `標題：${word}`), ...item.summary_matched_keywords.map(word => `摘要：${word}`)].join('、') })),
      ...result.parliament.map(item => ({ date: item.published_at.slice(0, 10), source: item.publisher, type: 'research', title: item.title, url: item.webpage_url, topics: item.matched_topics, score: item.relevance_score, reason: [...item.title_matched_keywords.map(word => `標題：${word}`), ...item.summary_matched_keywords.map(word => `摘要：${word}`)].join('、') })),
    ].filter(item => (!onlyFiltered || item.score >= result.summary.minimum_score) && (typeFilter === 'all' || item.type === typeFilter) && (sourceFilter === 'all' || item.source === sourceFilter) && item.score >= scoreFilter && `${item.title}${item.topics.join(' ')}${item.reason}`.toLowerCase().includes(resultQuery.toLowerCase()));
    values.sort((a, b) => sortKey === 'score' ? b.score - a.score : sortKey === 'source' ? a.source.localeCompare(b.source) : b.date.localeCompare(a.date));
    return values;
  }, [result, resultQuery, typeFilter, sourceFilter, scoreFilter, sortKey, onlyFiltered]);
  const resultSources = useMemo(() => [...new Set(result ? [...result.news.map(item => item.unit_category ?? ''), ...result.parliament.map(item => item.publisher)] : [])].filter(Boolean).sort(), [result]);

  async function choose() { const path = await save({ filters: [{ name: 'Excel', extensions: ['xlsx'] }], defaultPath: output }); if (path) { setCustomOutput(true); setOutput(path) } }
  function request(overrides?: Partial<{ since: string; until: string; output: string }>) { return buildRunRequest({ since: overrides?.since ?? since, until: overrides?.until ?? until, output: overrides?.output ?? output, workers, profile, calendar, selectedSources: [...selected], minimumScore }) }
  function acceptResult(value: Result) { setResult(value); setSelectedReportKey(reportKey(value.summary)); setPage('history') }
  async function run() { if (until < since) { setError('結束日期不得早於開始日期'); return } setRunning(true); setError(''); setProgress(null); try { acceptResult(await invoke<Result>('run_scraper', { request: request() })) } catch (reason) { setError(String(reason)) } finally { setRunning(false) } }
  async function retry(summary: Summary, summaryPath?: string) { const savedProfile = profiles.find(item => item.profile_id === summary.profile_id); if (!savedProfile) { setError('找不到此報表的主題設定檔，請先匯入原設定檔再重試。'); return } setRunning(true); setProgress(null); setError(''); try { const path = summaryPath ?? summary.output_file.replace(/\.xlsx$/i, '.run.json'); const retryRun = buildRunRequest({ since: summary.period_start, until: summary.period_end, output: summary.output_file, workers, profile: savedProfile, calendar: summary.excel_date_calendar ?? 'gregorian', selectedSources: summary.selected_sources ?? savedProfile.selected_sources, minimumScore: summary.minimum_score }); acceptResult(await invoke<Result>('retry_failed', { request: { run: retryRun, summaryPath: path } })) } catch (reason) { setError(String(reason)) } finally { setRunning(false) } }
  async function cancel() { if (await invoke<boolean>('cancel_run')) setError('執行已取消') }
  async function saveAsProfile() { if (!profile) return; const id = window.prompt('新設定檔 ID（小寫英數與連字號）', `${profile.profile_id}-copy`); if (!id) return; const name = window.prompt('設定檔名稱', `${profile.name} 副本`); if (!name) return; try { await invoke('save_profile', { profile: { ...profile, profile_id: id, name, selected_sources: [...selected], minimum_score: minimumScore } }); await refreshProfiles(id) } catch (reason) { setError(String(reason)) } }
  async function importProfile(event: React.ChangeEvent<HTMLInputElement>) { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ''; if (!file) return; try { const imported = parseProfileJson(await file.text()); if (profiles.some(item => item.profile_id === imported.profile_id) && !window.confirm(`覆寫設定檔「${imported.name}」？`)) return; await invoke('save_profile', { profile: imported }); await refreshProfiles(imported.profile_id); setError('') } catch (reason) { setError(String(reason)) } }
  async function removeProfile() { if (!profile || profile.profile_id === 'uk-tech-law' || !window.confirm(`刪除設定檔「${profile.name}」？`)) return; try { await invoke('delete_profile', { profileId: profile.profile_id }); await refreshProfiles() } catch (reason) { setError(String(reason)) } }
  function updateKeywords(topicIndex: number, strength: string, value: string) { if (!profile) return; const phrases = value.split(/[,，\n]/).map(item => item.trim()).filter(Boolean); setProfile({ ...profile, topics: profile.topics.map((topic, index) => index === topicIndex ? { ...topic, keywords: [...topic.keywords.filter(item => item.strength !== strength), ...phrases.map(phrase => ({ phrase, strength }))] } : topic) }) }

  return <main className="app-shell">
    <header className="app-header"><div className="brand"><img src={clockTower} alt="" className="brand-mark" /><span>UK 新聞與官方文件觀測</span><span className="brand-subtitle">Weekly Report Library</span></div><div className="header-tools"><time>{initial.until}（台北時間）</time><button className="icon-button" aria-label="使用說明" onClick={() => setHelpOpen(!helpOpen)}><Question /></button><button className="icon-button" disabled={running} aria-label="主題設定" onClick={() => setPage('settings')}><SlidersHorizontal /></button></div></header>
    <div className="app-body"><nav className="sidebar" aria-label="主要功能"><div className="nav-items">{([{ key: 'history', label: '執行紀錄', icon: ClockCounterClockwise }, { key: 'query', label: '新查詢', icon: MagnifyingGlass }, { key: 'settings', label: '主題設定', icon: SlidersHorizontal }] as const).map(item => <button key={item.key} className={page === item.key ? 'active' : ''} aria-current={page === item.key ? 'page' : undefined} disabled={running && page !== item.key} onClick={() => setPage(item.key)}><item.icon />{item.label}</button>)}</div><div className="sidebar-bottom"><button onClick={() => setHelpOpen(!helpOpen)}><Question />使用說明</button><button disabled={running} onClick={() => setPage(page === 'query' ? 'history' : 'query')}><ArrowLeft />{page === 'query' ? '回到執行紀錄' : '回到設定流程'}</button></div></nav>
    <div className="workspace">
    {designPreview && <p className="preview-banner" role="note">設計預覽 · 使用示例資料，操作不抓取新聞、不產生檔案。</p>}
    {error && <div className="error" role="alert">{error}<button aria-label="關閉錯誤訊息" onClick={() => setError('')}>關閉</button></div>}
    {previewNotice && <div className="preview-notice" role="status">{previewNotice}<button onClick={() => setPreviewNotice('')}>關閉</button></div>}
    {helpOpen && <section className="help-panel" aria-label="使用說明"><h2>從查詢到每週報表</h2><p>先在「新查詢」選擇主題、期間與官方來源，再開始執行。完成後可在「執行紀錄」開啟 Excel，查看來源健康，或僅重試異常來源。</p><p>「來源需注意」表示已保留可用資料；零筆資料不一定代表失敗。主題設定與匯入規則在「主題設定」管理。</p><button onClick={() => setHelpOpen(false)}>收合說明</button></section>}
    {running && <section className="run-progress" role="status"><div><h2>{progress?.message ?? '正在準備執行'}{progress?.source && `：${progress.source}`}</h2><button onClick={cancel}>取消執行</button></div><progress value={progress?.kind === 'completed' ? 100 : progress?.kind === 'exporting' ? 95 : progress?.kind === 'translating' ? 90 : progress?.kind === 'filtering' ? 85 : progress?.total ? Math.round(progress.completed / progress.total * 80) : undefined} max={100} /><small>{progress ? `${progress.completed}／${progress.total} 個來源已完成` : '正在連接來源，已取得的資料將保留於完成報表。'}</small></section>}
    {page === 'history' && <ReportLibrary reports={reports} selected={activeReport} running={running} showAllHealth={showHealth} onSelect={selectLibraryReport} onCreate={() => setPage('query')} onOpen={item => { void openPath(item.output_file).catch(reason => setError(String(reason))) }} onRetry={item => { void retry(item, result && reportKey(result.summary) === reportKey(item) ? result.summary_path : undefined) }} onToggleHealth={() => setShowHealth(!showHealth)} onPreview={result && activeReport && reportKey(activeReport) === reportKey(result.summary) ? () => setPage('results') : undefined} />}
    {page === 'query' && <><div className="page-heading"><div><h1>建立新聞查詢</h1><p>設定本次期間與來源，收集新聞、官方文件及國會研究。</p></div></div><fieldset disabled={running}><section className="grid">
      <div className="panel"><h2>執行設定</h2>
        <label>主題設定檔<select value={profile?.profile_id ?? ''} onChange={event => { const value = profiles.find(item => item.profile_id === event.target.value); if (value) selectProfile(value) }}>{profiles.map(item => <option key={item.profile_id} value={item.profile_id}>{item.name}</option>)}</select></label>
        <button className="text-button" onClick={() => setPage('settings')}>管理主題設定</button>
        <div className="date-presets" role="group" aria-label="常用查詢期間">{[7, 14, 30].map(days => <button type="button" key={days} disabled={running} onClick={() => { const period = defaultPeriod(new Date(), days); setSince(period.since); setUntil(period.until) }}>最近 {days} 天</button>)}</div>
        <div className="dates"><label>開始日期<input type="date" value={since} onInput={event => setSince(event.currentTarget.value)} onChange={event => setSince(event.target.value)} /></label><label>結束日期<input type="date" value={until} onInput={event => setUntil(event.currentTarget.value)} onChange={event => setUntil(event.target.value)} /></label></div>
        {until < since && <p className="date-error" role="alert">結束日期不得早於開始日期。</p>}
        <details className="advanced-options"><summary>進階選項</summary><label>最低相關性分數<input type="number" min="1" max="99" value={minimumScore} onChange={event => setMinimumScore(Number(event.target.value))} /></label>
        <label>機關來源併發數<select value={workers} disabled={running} onChange={event => setWorkers(Number(event.target.value))}>{workerChoices.map(count => <option key={count} value={count}>{count} 個來源</option>)}</select></label>
        <label>Excel 日期<select value={calendar} onChange={event => setCalendar(event.target.value)}><option value="gregorian">西元</option><option value="roc">民國</option></select></label>
        </details><label>輸出檔<div className="file"><input value={output} onChange={event => { setCustomOutput(true); setOutput(event.target.value) }} /><button disabled={running} onClick={choose}>選擇</button></div></label>
        <button className="primary run" disabled={running || !output || selected.size === 0 || until < since} onClick={run}><Plus />{running ? '執行中' : '開始查詢'}</button>
      </div>
      <div className="panel sources"><div className="source-head"><div><h2>官方來源</h2><small>{selected.size} 個來源已選取 · 目錄 {sources.length} 筆</small></div><input placeholder="搜尋機關、團體或法院" value={query} onChange={event => { setQuery(event.target.value); setSourceLimit(60) }} /></div><label>地區<select value={jurisdiction} onChange={event => { setJurisdiction(event.target.value); setSourceLimit(60) }}><option value="all">全部地區</option><option value="UK">英國中央</option><option value="Scotland">蘇格蘭</option><option value="Wales">威爾斯</option><option value="England and Wales">英格蘭及威爾斯法院</option><option value="Northern Ireland">北愛爾蘭</option></select></label><div className="cards">{shown.map(source => <label className="source" key={source.short_name} title={source.searchable ? source.homepage : source.reason}><input type="checkbox" disabled={!source.searchable} checked={selected.has(source.short_name)} onChange={() => setSelected(previous => { const next = new Set(previous); next.has(source.short_name) ? next.delete(source.short_name) : next.add(source.short_name); return next })} /><span><strong>{source.name_zh}</strong><em>{source.name_en}</em><small>JSON ID：{source.short_name}</small><small>{source.jurisdiction} · {source.kind} · {source.searchable ? '可查詢' : '僅列名：' + source.reason}</small></span></label>)}</div>{matchingSources.length > shown.length && <button type="button" onClick={() => setSourceLimit(value => value + 60)}>顯示更多（尚有 {matchingSources.length - shown.length} 筆）</button>}</div>
    </section></fieldset></>}
    {page === 'settings' && <><div className="page-heading"><div><h1>主題設定</h1><p>管理查詢主題與關鍵詞，沿用或另存常用設定。</p></div><button className="primary" disabled={running} onClick={() => setPage('query')}><MagnifyingGlass />使用此設定查詢</button></div><section className="settings-profile"><label>主題設定檔<select value={profile?.profile_id ?? ''} onChange={event => { const value = profiles.find(item => item.profile_id === event.target.value); if (value) selectProfile(value) }}>{profiles.map(item => <option key={item.profile_id} value={item.profile_id}>{item.name}</option>)}</select></label><p>{profile?.description}</p><div className="profile-actions"><button onClick={saveAsProfile}>另存設定檔</button><button onClick={() => profileImportRef.current?.click()}>匯入 JSON</button><input ref={profileImportRef} type="file" accept=".json,application/json" hidden onChange={importProfile} /><button onClick={() => openUrl('https://github.com/ECJura2000/UK-news-scraper/releases/latest/download/UKNewsScraper-Topic-Profile-Example.json')}>下載範例 JSON</button><button disabled={profile?.profile_id === 'uk-tech-law'} onClick={removeProfile}>刪除設定檔</button></div></section>
    {profile && <section className="panel keyword-editor"><h2>關鍵詞規則</h2><p>可用逗號或換行分隔；變更會套用於本次執行，另存設定檔後可重複使用。</p>{profile.topics.map((topic, index) => <details key={topic.name}><summary>{topic.name}</summary><div className="keyword-grid">{['core', 'general', 'supporting'].map(strength => <label key={strength}>{strength === 'core' ? '核心' : strength === 'general' ? '一般' : '輔助'}<textarea value={topic.keywords.filter(item => item.strength === strength).map(item => item.phrase).join(', ')} onChange={event => updateKeywords(index, strength, event.target.value)} /></label>)}</div></details>)}</section>}</>}
    {page === 'results' && result && <div className="page-heading"><div><h1>新聞結果</h1><p>{result.summary.period_start} 至 {result.summary.period_end} · {result.summary.profile_name ?? result.summary.profile_id}</p></div><button onClick={() => setPage('history')}><ArrowLeft />回到報表</button></div>}
    <div hidden={page !== 'results'}>
    {result && <section className="panel preview"><div className="preview-head"><h2>結果預覽 <small>{rows.length} 筆</small></h2><input placeholder="搜尋標題、主題或命中詞" value={resultQuery} onChange={event => setResultQuery(event.target.value)} /><select aria-label="入選範圍" value={onlyFiltered ? 'filtered' : 'all'} onChange={event => setOnlyFiltered(event.target.value === 'filtered')}><option value="filtered">初步篩選</option><option value="all">全部資料</option></select><select value={typeFilter} onChange={event => setTypeFilter(event.target.value)}><option value="all">全部類型</option><option value="news">news</option><option value="guidance">guidance</option><option value="report">report</option><option value="publication">publication</option><option value="judgment">judgment</option><option value="research">research</option></select><select value={sourceFilter} onChange={event => setSourceFilter(event.target.value)}><option value="all">全部來源</option>{resultSources.map(source => <option key={source}>{source}</option>)}</select><input aria-label="最低分數" type="number" min="0" value={scoreFilter} onChange={event => setScoreFilter(Number(event.target.value))} /><select value={sortKey} onChange={event => setSortKey(event.target.value as typeof sortKey)}><option value="date">日期排序</option><option value="score">分數排序</option><option value="source">來源排序</option></select></div><div className="table-wrap"><table><thead><tr><th>日期</th><th>類型</th><th>來源</th><th>標題</th><th>主題與命中原因</th><th>分數</th></tr></thead><tbody>{rows.map((item, index) => <tr key={`${item.url}-${index}`}><td>{item.date}</td><td>{item.type}</td><td>{item.source}</td><td><button className="link" onClick={() => openUrl(item.url)}>{item.title}</button></td><td>{item.topics.join('、')}<small className="match-reason">{item.reason || '未命中'}</small></td><td>{item.score}</td></tr>)}</tbody></table></div></section>}
    </div>
    </div></div>
  </main>
}

export default App;
