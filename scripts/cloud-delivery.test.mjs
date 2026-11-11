import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { dateInputs, inspect, stage } from './cloud-delivery.mjs';

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'news-cloud-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}
const sha = (p) => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
function pair(root) {
  fs.mkdirSync(path.join(root, 'reports'));
  const output_file = path.join(root, '本週新聞.xlsx');
  const report_file = path.join(root, 'reports/news_scraper_run_test.json');
  fs.writeFileSync(output_file, 'fixture workbook');
  fs.writeFileSync(report_file, JSON.stringify({ run_id: 'test', output_file, status: 'partial_failure', failed_sources: ['fixture'] }));
  const manifest = { run_id: 'test', output_file, report_file, excel_sha256: sha(output_file), report_sha256: sha(report_file) };
  fs.writeFileSync(report_file.replace('.json', '.complete'), JSON.stringify(manifest));
  fs.writeFileSync(path.join(root, 'reports/latest_run.json'), JSON.stringify(manifest));
  return { output_file, report_file };
}

test('rejects partial dates, reversed ranges, impossible dates and shell text', () => {
  for (const env of [
    { START_DATE: '2026-10-01' },
    { START_DATE: '2026-10-03', END_DATE: '2026-10-01' },
    { START_DATE: '2026-02-30', END_DATE: '2026-03-01' },
    { START_DATE: '$(touch injected)', END_DATE: '2026-10-01' },
    { DAYS: '0' }, { DAYS: '367' }, { DAYS: '7;echo injected' },
  ]) assert.throws(() => dateInputs(env));
  assert.deepEqual(dateInputs({ START_DATE: '2026-10-01', END_DATE: '2026-10-01' }),
    { start: '2026-10-01', end: '2026-10-01', days: '7' });
  assert.equal(dateInputs({}).days, '7');
});

test('Taiwan stages a completed partial result with original evidence', (t) => {
  const root = fixture(t);
  pair(root);
  const dest = path.join(root, 'staged');
  assert.equal(stage('taiwan', root, dest), 'partial_failure');
  assert.equal(fs.readdirSync(dest).length, 4);
});

test('Taiwan rejects a missing completion marker', (t) => {
  const root = fixture(t);
  const { report_file } = pair(root);
  fs.unlinkSync(report_file.replace('.json', '.complete'));
  assert.throws(() => inspect('taiwan', root));
});

test('Taiwan rejects workbook or JSON tampering', (t) => {
  for (const field of ['output_file', 'report_file']) {
    const root = fixture(t);
    const p = pair(root);
    fs.appendFileSync(p[field], 'tamper');
    assert.throws(() => inspect('taiwan', root));
  }
});

test('Taiwan rejects mismatched pointer and completion marker', (t) => {
  const root = fixture(t);
  pair(root);
  const pointer = path.join(root, 'reports/latest_run.json');
  const manifest = JSON.parse(fs.readFileSync(pointer));
  manifest.run_id = 'another-run';
  fs.writeFileSync(pointer, JSON.stringify(manifest));
  assert.throws(() => inspect('taiwan', root));
});

test('UK preserves degraded reports and rejects paths outside run directory', (t) => {
  const root = fixture(t);
  const workbook = path.join(root, 'UK新聞查詢.xlsx');
  const report = path.join(root, 'UK新聞查詢.run.json');
  fs.writeFileSync(workbook, 'fixture');
  fs.writeFileSync(report, JSON.stringify({ run_id: 'uk-test', status: 'degraded', output_file: workbook }));
  assert.equal(inspect('uk', root).report.status, 'degraded');
  const external = path.join(fixture(t), 'external.xlsx');
  fs.writeFileSync(external, 'fixture');
  fs.writeFileSync(report, JSON.stringify({ run_id: 'uk-test', status: 'degraded', output_file: external }));
  assert.throws(() => inspect('uk', root));
});
