import { ArrowSquareOut, ArrowClockwise, CheckCircle, Warning, CaretRight, FileXls, MagnifyingGlass, Plus } from '@phosphor-icons/react';
import { needsRetry, reportKey, reportStatus, reportTimestamp, type Summary } from './reportModel';

type Props = {
  reports: Summary[]; selected?: Summary; running: boolean; showAllHealth: boolean;
  onSelect: (summary: Summary) => void; onCreate: () => void; onOpen: (summary: Summary) => void;
  onRetry: (summary: Summary) => void; onToggleHealth: () => void; onPreview?: () => void;
};

export function ReportLibrary({ reports, selected, running, showAllHealth, onSelect, onCreate, onOpen, onRetry, onToggleHealth, onPreview }: Props) {
  const health = selected ? [...selected.source_health].sort((a, b) => Number(!b.success || Boolean(b.warning)) - Number(!a.success || Boolean(a.warning))) : [];
  return <section className="report-page">
    <div className="page-heading"><div><h1>每週報表</h1><p>檢視查詢紀錄與產出結果，開啟 Excel，或查看需要重試的來源。</p></div><button className="primary" disabled={running} onClick={onCreate}><Plus />新增查詢</button></div>
    {reports.length === 0 ? <div className="empty-library"><FileXls size={44} /><h2>還沒有報表</h2><p>使用內建科技法制設定，開始第一次新聞查詢。</p><button className="primary" disabled={running} onClick={onCreate}>建立新聞查詢</button><small>執行紀錄依目前輸出資料夾顯示。</small></div> : <div className="report-columns">
      <div className="report-list"><div className="table-wrap"><table aria-label="每週報表列表"><thead><tr><th>期間</th><th>執行日期</th><th>主題設定</th><th>狀態</th><th><span className="sr-only">查看報表</span></th></tr></thead><tbody>{reports.map(item => <tr key={reportKey(item)} className={selected && reportKey(selected) === reportKey(item) ? 'selected' : ''}><td><button className="report-select" aria-pressed={Boolean(selected && reportKey(selected) === reportKey(item))} disabled={running} onClick={() => onSelect(item)}>{item.period_start.replaceAll('-', '/')}<span>– {item.period_end.replaceAll('-', '/')}</span></button></td><td><time dateTime={item.generated_at}>{reportTimestamp(item.generated_at)}</time></td><td>{item.profile_name ?? item.profile_id}</td><td><span className={`status ${item.status === 'complete' ? 'healthy' : 'attention'}`}>{item.status === 'complete' ? <CheckCircle weight="fill" /> : <Warning weight="fill" />}{reportStatus(item)}</span></td><td><button className="icon-button" disabled={running} aria-label={`查看 ${item.period_start} 至 ${item.period_end} 報表`} onClick={() => onSelect(item)}><CaretRight /></button></td></tr>)}</tbody></table></div><div className="list-footer"><span>共 {reports.length} 筆 · 台北時間</span><span>筆數依執行摘要</span></div></div>
      {selected && <aside className="report-detail" aria-label="所選報表詳情"><p className="detail-label">報表期間</p><h2>{selected.period_start.replaceAll('-', '/')} – {selected.period_end.replaceAll('-', '/')}</h2><p className="profile-description">主題設定 <b>{selected.profile_name ?? selected.profile_id}</b></p>
        <div className={`report-notice ${selected.status === 'complete' ? 'complete' : 'warning'}`} role="status">{selected.status === 'complete' ? <CheckCircle size={30} weight="fill" /> : <Warning size={30} weight="fill" />}<div><h3>{selected.status === 'complete' ? 'Excel 已產生，來源完整' : selected.status === 'degraded' ? 'Excel 已產生，部分來源需注意' : '執行未完成'}</h3><p>{selected.status === 'complete' ? '可開啟報表，檢視本期收錄資料。' : '成功取得的資料已保留；請檢視以下來源。'}</p></div></div>
        <dl className="report-counts"><div><dt>全部新聞</dt><dd>{selected.all_news_count}<small>篇</small></dd></div><div><dt>初步篩選</dt><dd>{selected.filtered_news_count}<small>篇</small></dd></div><div><dt>國會研究</dt><dd>{selected.parliament_count}<small>篇</small></dd></div></dl>
        <div className="detail-actions"><button className="primary" disabled={selected.status !== 'complete' && selected.status !== 'degraded'} onClick={() => onOpen(selected)}><FileXls />開啟 Excel</button><button disabled={running || !needsRetry(selected)} onClick={() => onRetry(selected)}><ArrowClockwise />重試異常來源</button></div>
        {onPreview && <button className="text-button preview-action" onClick={onPreview}><MagnifyingGlass />檢視本次新聞結果<ArrowSquareOut size={15} /></button>}
        <section className="health-section"><div className="section-heading"><h3>來源健康狀態</h3><small>國會初步篩選 {selected.filtered_parliament_count} 篇</small></div><div className="health-table-wrap"><table aria-label="來源健康狀態"><thead><tr><th>來源</th><th>狀態</th><th>說明</th></tr></thead><tbody>{(showAllHealth ? health : health.slice(0, 5)).map(item => <tr key={item.source}><td>{item.source}</td><td><span className={`status ${!item.success ? 'failed' : item.warning ? 'attention' : 'healthy'}`}>{item.success && !item.warning ? <CheckCircle weight="fill" /> : <Warning weight="fill" />}{!item.success ? '失敗' : item.warning ? '需注意' : '正常'}</span></td><td>{item.warning || '順利取得資料'}<small>{item.item_count} 筆 · {item.duration_seconds.toFixed(1)} 秒</small></td></tr>)}</tbody></table></div>{health.length > 5 && <button className="text-button" onClick={onToggleHealth}>{showAllHealth ? '收合來源' : `查看全部 ${health.length} 個來源`}</button>}
        {selected.warnings.length > 0 && <details className="run-warnings"><summary>執行提醒（{selected.warnings.length}）</summary><ul>{selected.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
        {selected.observability && <p className="observability">來源成功率 {Math.round(selected.observability.source_success_rate * 100)}% · 零筆來源 {Math.round(selected.observability.zero_item_ratio * 100)}%<small>零筆可能代表期間內未發布資料，不等同來源失敗。</small></p>}
        </section>
      </aside>}
    </div>}
  </section>;
}
