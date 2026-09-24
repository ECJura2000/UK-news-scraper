import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { save } from '@tauri-apps/plugin-dialog';
import { openPath, openUrl } from '@tauri-apps/plugin-opener';
import { defaultPeriod } from './period';
import './style.css';
import './extras.css';

type Agency = { short_name: string; name_zh: string; name_en: string; topics: string[] };
type Keyword = { phrase: string; strength: string };
type Profile = { profile_id: string; name: string; description: string; version: number; selected_sources: string[]; topics: { name: string; keywords: Keyword[] }[]; minimum_score: number };
type ProfileReport = { profiles: Profile[]; warning: string; recovery_path: string | null };
type SourceHealth = { source: string; critical: boolean; success: boolean; item_count: number; duration_seconds: number; warning: string };
type Summary = { run_id: string; status: string; period_start: string; period_end: string; output_file: string; profile_id: string; minimum_score: number; all_news_count: number; filtered_news_count: number; parliament_count: number; filtered_parliament_count: number; source_health: SourceHealth[]; warnings: string[] };
type News = { published_at: string; unit_category: string | null; title: string; link: string; content_type: string; matched_topics: string[]; matched_keywords: string[]; title_matched_keywords: string[]; summary_matched_keywords: string[]; relevance_score: number };
type Parliament = { published_at: string; publisher: string; title: string; webpage_url: string; matched_topics: string[]; matched_keywords: string[]; title_matched_keywords: string[]; summary_matched_keywords: string[]; relevance_score: number };
type Result = { workbook_path: string; summary_path: string; summary: Summary; news: News[]; parliament: Parliament[] };
type PreviewRow = { date: string; source: string; type: string; title: string; url: string; topics: string[]; score: number; reason: string };
type RunProgress = { kind: string; completed: number; total: number; source: string; message: string };

const outputDirectory = (path: string) => { const value = path.replace(/[\\/][^\\/]+$/, ''); return value === path ? '.' : value };

function App() {
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
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [history, setHistory] = useState<Summary[]>([]);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [resultQuery, setResultQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [scoreFilter, setScoreFilter] = useState(0);
  const [sortKey, setSortKey] = useState<'date' | 'score' | 'source'>('date');
  const [onlyFiltered, setOnlyFiltered] = useState(true);
  const [progress, setProgress] = useState<RunProgress | null>(null);
  const [showHealth, setShowHealth] = useState(false);

  function selectProfile(value: Profile) { setProfile(value); setSelected(new Set(value.selected_sources)); setMinimumScore(value.minimum_score) }
  async function refreshProfiles(preferred?: string) { const values = await invoke<Profile[]>('list_profiles'); setProfiles(values); const next = values.find(item => item.profile_id === preferred) ?? values[0]; if (next) selectProfile(next) }

  useEffect(() => { Promise.all([invoke<Agency[]>('source_catalog'), invoke<ProfileReport>('profile_load_report')]).then(([catalog, report]) => { setSources([...catalog, { short_name: 'UK Parliament', name_zh: '英國國會研究資料', name_en: 'UK Parliament Research Briefings', topics: ['Commons Library', 'Lords Library', 'POST'] }]); setProfiles(report.profiles); if (report.profiles[0]) selectProfile(report.profiles[0]); if (report.warning) setError(report.warning) }).catch(reason => setError(String(reason))) }, []);
  useEffect(() => { let active = true; let unlisten: (() => void) | undefined; listen<RunProgress>('scraper-progress', event => { if (active) setProgress(event.payload) }).then(stop => { if (active) unlisten = stop; else stop() }); return () => { active = false; unlisten?.() } }, []);
  useEffect(() => { if (!customOutput && profile) invoke<string>('suggested_output', { since, until, profileId: profile.profile_id }).then(setOutput).catch(reason => setError(String(reason))) }, [since, until, profile?.profile_id, customOutput]);
  useEffect(() => { invoke<Summary[]>('recent_runs', { outputDir: outputDirectory(output) }).then(setHistory).catch(() => setHistory([])) }, [output, result]);
  const shown = useMemo(() => sources.filter(source => `${source.short_name}${source.name_zh}${source.name_en}`.toLowerCase().includes(query.toLowerCase())), [sources, query]);
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
  function request(overrides?: Partial<{ since: string; until: string; output: string }>) { return { since: overrides?.since ?? since, until: overrides?.until ?? until, output: overrides?.output ?? output, workers: 6, profilePath: profile?.profile_id ?? null, calendar, selectedSources: [...selected], minimumScore, profile: profile ? { ...profile, selected_sources: [...selected], minimum_score: minimumScore } : null } }
  async function run() { if (until < since) { setError('結束日期不得早於開始日期'); return } setRunning(true); setError(''); setResult(null); setProgress(null); try { setResult(await invoke<Result>('run_scraper', { request: request() })) } catch (reason) { setError(String(reason)) } finally { setRunning(false) } }
  async function retry(summary: Summary, summaryPath?: string) { setRunning(true); setError(''); try { const path = summaryPath ?? summary.output_file.replace(/\.xlsx$/i, '.run.json'); setResult(await invoke<Result>('retry_failed', { request: { run: request({ since: summary.period_start, until: summary.period_end, output: summary.output_file }), summaryPath: path } })) } catch (reason) { setError(String(reason)) } finally { setRunning(false) } }
  async function cancel() { if (await invoke<boolean>('cancel_run')) setError('執行已取消') }
  async function saveAsProfile() { if (!profile) return; const id = window.prompt('新設定檔 ID（小寫英數與連字號）', `${profile.profile_id}-copy`); if (!id) return; const name = window.prompt('設定檔名稱', `${profile.name} 副本`); if (!name) return; try { await invoke('save_profile', { profile: { ...profile, profile_id: id, name, selected_sources: [...selected], minimum_score: minimumScore } }); await refreshProfiles(id) } catch (reason) { setError(String(reason)) } }
  async function removeProfile() { if (!profile || profile.profile_id === 'uk-tech-law' || !window.confirm(`刪除設定檔「${profile.name}」？`)) return; try { await invoke('delete_profile', { profileId: profile.profile_id }); await refreshProfiles() } catch (reason) { setError(String(reason)) } }
  function updateKeywords(topicIndex: number, strength: string, value: string) { if (!profile) return; const phrases = value.split(/[,，\n]/).map(item => item.trim()).filter(Boolean); setProfile({ ...profile, topics: profile.topics.map((topic, index) => index === topicIndex ? { ...topic, keywords: [...topic.keywords.filter(item => item.strength !== strength), ...phrases.map(phrase => ({ phrase, strength }))] } : topic) }) }

  return <main>
    <header><div><p className="eyebrow">UK OFFICIAL INTELLIGENCE</p><h1>英國新聞與官方文件觀測</h1><p>官方來源、政策文件與國會研究</p></div><span className="badge">桌面版</span></header>
    <section className="grid">
      <div className="panel"><h2>執行設定</h2>
        <label>主題設定檔<select value={profile?.profile_id ?? ''} onChange={event => { const value = profiles.find(item => item.profile_id === event.target.value); if (value) selectProfile(value) }}>{profiles.map(item => <option key={item.profile_id} value={item.profile_id}>{item.name}</option>)}</select></label>
        <div className="profile-actions"><button onClick={saveAsProfile}>另存設定檔</button><button disabled={profile?.profile_id === 'uk-tech-law'} onClick={removeProfile}>刪除</button></div>
        <div className="date-presets" role="group" aria-label="常用查詢期間">{[7, 14, 30].map(days => <button type="button" key={days} disabled={running} onClick={() => { const period = defaultPeriod(new Date(), days); setSince(period.since); setUntil(period.until) }}>最近 {days} 天</button>)}</div>
        <div className="dates"><label>開始日期<input type="date" value={since} onChange={event => setSince(event.target.value)} /></label><label>結束日期<input type="date" value={until} onChange={event => setUntil(event.target.value)} /></label></div>
        <label>最低相關性分數<input type="number" min="1" max="99" value={minimumScore} onChange={event => setMinimumScore(Number(event.target.value))} /></label>
        <label>Excel 日期<select value={calendar} onChange={event => setCalendar(event.target.value)}><option value="gregorian">西元</option><option value="roc">民國</option></select></label>
        <label>輸出檔<div className="file"><input value={output} onChange={event => { setCustomOutput(true); setOutput(event.target.value) }} /><button onClick={choose}>選擇</button></div></label>
        {running ? <button className="run cancel" onClick={cancel}>取消執行</button> : <button className="run" disabled={!output || selected.size === 0 || until < since} onClick={run}>開始執行</button>}{error && <pre className="error">{error}</pre>}
        {running && progress && <div className="run-progress" role="status"><p>{progress.message}{progress.source && `：${progress.source}`}</p><progress value={progress.kind === 'completed' ? 100 : progress.kind === 'exporting' ? 95 : progress.kind === 'translating' ? 90 : progress.kind === 'filtering' ? 85 : progress.total ? Math.round(progress.completed / progress.total * 80) : 0} max={100} /><small>{progress.completed}／{progress.total} 個來源已完成</small></div>}
      </div>
      <div className="panel sources"><div className="source-head"><div><h2>官方來源</h2><small>{selected.size} 個來源已選取</small></div><input placeholder="搜尋來源" value={query} onChange={event => setQuery(event.target.value)} /></div><div className="cards">{shown.map(source => <label className="source" key={source.short_name}><input type="checkbox" checked={selected.has(source.short_name)} onChange={() => setSelected(previous => { const next = new Set(previous); next.has(source.short_name) ? next.delete(source.short_name) : next.add(source.short_name); return next })} /><span><strong>{source.short_name}</strong><em>{source.name_zh}</em><small>{source.topics.join(' · ')}</small></span></label>)}</div></div>
    </section>
    {profile && <section className="profile"><b>{profile.name}</b><span>{profile.description}</span><span>最低分數 {minimumScore}</span></section>}
    {profile && <section className="panel keyword-editor"><h2>關鍵詞規則</h2><p>可用逗號或換行分隔；變更會套用於本次執行，另存設定檔後可重複使用。</p>{profile.topics.map((topic, index) => <details key={topic.name}><summary>{topic.name}</summary><div className="keyword-grid">{['core', 'general', 'supporting'].map(strength => <label key={strength}>{strength === 'core' ? '核心' : strength === 'general' ? '一般' : '輔助'}<textarea value={topic.keywords.filter(item => item.strength === strength).map(item => item.phrase).join(', ')} onChange={event => updateKeywords(index, strength, event.target.value)} /></label>)}</div></details>)}</section>}
    {result && <section className="result"><div><p className="eyebrow">執行結果</p><h2>{result.summary.status === 'complete' ? '執行完成' : '降級完成，請檢查來源'}</h2><p>{result.summary.period_start} 至 {result.summary.period_end}</p></div><div className="metrics"><b>{result.summary.all_news_count}<small>全部新聞</small></b><b>{result.summary.filtered_news_count}<small>初步篩選</small></b><b>{result.summary.parliament_count}<small>國會研究</small></b></div><div className="result-actions"><button onClick={() => openPath(result.workbook_path)}>開啟 Excel</button><button onClick={() => setShowHealth(!showHealth)}>{showHealth ? '收合' : '查看'}來源健康</button>{result.summary.warnings.length > 0 && <button disabled={running} onClick={() => retry(result.summary, result.summary_path)}>重試異常來源</button>}</div>{showHealth && <div className="health-list">{result.summary.source_health.map(health => <article key={health.source}><strong>{health.source}：{!health.success ? '失敗' : health.warning ? '需注意' : '正常'}</strong><span>{health.item_count} 筆 · {health.duration_seconds} 秒</span>{health.warning && <small>{health.warning}</small>}</article>)}</div>}</section>}
    {result && <section className="panel preview"><div className="preview-head"><h2>結果預覽 <small>{rows.length} 筆</small></h2><input placeholder="搜尋標題、主題或命中詞" value={resultQuery} onChange={event => setResultQuery(event.target.value)} /><select aria-label="入選範圍" value={onlyFiltered ? 'filtered' : 'all'} onChange={event => setOnlyFiltered(event.target.value === 'filtered')}><option value="filtered">初步篩選</option><option value="all">全部資料</option></select><select value={typeFilter} onChange={event => setTypeFilter(event.target.value)}><option value="all">全部類型</option><option value="news">news</option><option value="guidance">guidance</option><option value="report">report</option><option value="publication">publication</option><option value="research">research</option></select><select value={sourceFilter} onChange={event => setSourceFilter(event.target.value)}><option value="all">全部來源</option>{resultSources.map(source => <option key={source}>{source}</option>)}</select><input aria-label="最低分數" type="number" min="0" value={scoreFilter} onChange={event => setScoreFilter(Number(event.target.value))} /><select value={sortKey} onChange={event => setSortKey(event.target.value as typeof sortKey)}><option value="date">日期排序</option><option value="score">分數排序</option><option value="source">來源排序</option></select></div><div className="table-wrap"><table><thead><tr><th>日期</th><th>類型</th><th>來源</th><th>標題</th><th>主題與命中原因</th><th>分數</th></tr></thead><tbody>{rows.map((item, index) => <tr key={`${item.url}-${index}`}><td>{item.date}</td><td>{item.type}</td><td>{item.source}</td><td><button className="link" onClick={() => openUrl(item.url)}>{item.title}</button></td><td>{item.topics.join('、')}<small className="match-reason">{item.reason || '未命中'}</small></td><td>{item.score}</td></tr>)}</tbody></table></div></section>}
    <section className="panel history"><h2>最近執行</h2>{history.length === 0 ? <p>這個輸出資料夾尚無執行紀錄。</p> : history.map(item => <article key={`${item.run_id}-${item.output_file}`}><span><b>{item.period_start} 至 {item.period_end}</b><small>{item.status} · {item.all_news_count} 筆</small></span><div><button onClick={() => openPath(item.output_file)}>開啟</button>{item.warnings.length > 0 && <button disabled={running} onClick={() => retry(item)}>重試異常</button>}</div></article>)}</section>
  </main>
}

createRoot(document.getElementById('root')!).render(<App />);
