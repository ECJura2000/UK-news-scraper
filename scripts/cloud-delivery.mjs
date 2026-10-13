import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

export function dateInputs(env) {
  const start = env.START_DATE || '';
  const end = env.END_DATE || '';
  if (Boolean(start) !== Boolean(end)) throw new Error('起訖日期必須同時填寫或同時留白');
  for (const value of [start, end].filter(Boolean)) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(value)) ||
        new Date(value).toISOString().slice(0, 10) !== value) throw new Error('日期須為有效 YYYY-MM-DD');
  }
  if (start && start > end) throw new Error('起日不得晚於迄日');
  const days = env.DAYS || '7';
  if (!/^\d+$/.test(days) || Number(days) < 1 || Number(days) > 366) throw new Error('回推天數限 1–366');
  return { start, end, days };
}

const read = (filename) => JSON.parse(fs.readFileSync(filename, 'utf8'));
const hash = (filename) => crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex');
function inside(root, filename) {
  const resolved = fs.realpathSync(filename);
  const relative = path.relative(fs.realpathSync(root), resolved);
  if (relative.startsWith('..') || path.isAbsolute(relative) || !fs.statSync(resolved).isFile()) {
    throw new Error('報表路徑必須位於本次 output 資料夾');
  }
  return resolved;
}

export function inspect(kind, root) {
  let reportPath, workbookPath, report, files;
  if (kind === 'uk') {
    reportPath = path.join(root, 'UK新聞查詢.run.json');
    report = read(reportPath);
    workbookPath = inside(root, report.output_file);
    if (!['complete', 'degraded'].includes(report.status) || !report.run_id) throw new Error('英國摘要格式錯誤');
    files = [workbookPath, inside(root, reportPath)];
  } else if (kind === 'taiwan') {
    const pointerPath = path.join(root, 'reports', 'latest_run.json');
    const pointer = read(pointerPath); // Read once; verify marker and both checksums.
    reportPath = inside(root, pointer.report_file);
    workbookPath = inside(root, pointer.output_file);
    const markerPath = inside(root, reportPath.replace(/\.json$/, '.complete'));
    const marker = read(markerPath);
    for (const key of ['run_id', 'output_file', 'report_file', 'excel_sha256', 'report_sha256']) {
      if (!pointer[key] || pointer[key] !== marker[key]) throw new Error('完成標記與 latest 指標不一致');
    }
    report = read(reportPath);
    if (report.run_id !== pointer.run_id || report.output_file !== pointer.output_file ||
        hash(workbookPath) !== pointer.excel_sha256 || hash(reportPath) !== pointer.report_sha256) {
      throw new Error('報表配對或 SHA-256 驗證失敗');
    }
    if (!['success', 'attention', 'partial_failure'].includes(report.status)) throw new Error('台灣摘要狀態錯誤');
    files = [workbookPath, reportPath, markerPath, inside(root, pointerPath)];
  } else throw new Error('未知專案類型');
  if (path.extname(workbookPath) !== '.xlsx' || fs.statSync(workbookPath).size === 0) throw new Error('缺少 Excel');
  return { report, files };
}

export function stage(kind, root, destination) {
  const { report, files } = inspect(kind, root);
  fs.mkdirSync(destination, { recursive: true });
  for (const filename of files) fs.copyFileSync(filename, path.join(destination, path.basename(filename)));
  const details = kind === 'uk'
    ? { all_news_count: report.all_news_count, filtered_news_count: report.filtered_news_count,
        parliament_count: report.parliament_count, warnings: report.warnings }
    : { news_count: report.news_count, failed_sources: report.failed_sources,
        anomalies: report.anomalies, error_counts: report.error_counts,
        alert_reasons: report.quality?.alert_reasons, ruleset_hash: report.relevance_policy?.ruleset_hash };
  const markdown = `## 新聞雲端執行結果\n\n抓取狀態：**${report.status}**。檔案保存成功與來源完整性分別判讀。\n\n` +
    '```json\n' + JSON.stringify(details, null, 2) + '\n```\n';
  if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, markdown);
  if (!['complete', 'success'].includes(report.status)) console.log('::warning::部分來源或品質有警告，請查看執行摘要與 JSON');
  return report.status;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    if (process.argv[2] === 'validate-inputs') dateInputs(process.env);
    else stage(process.argv[2], process.argv[3] || 'output', process.argv[4] || 'cloud-publish');
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
