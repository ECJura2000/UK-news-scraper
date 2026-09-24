import { describe, expect, it } from 'vitest';
import { parseProfileJson } from './profileImport';

const example = {
  profile_id: 'uk-custom-ai',
  name: '自訂 AI',
  description: '',
  version: 1,
  selected_sources: ['BIST'],
  topics: [{ name: 'AI', keywords: [{ phrase: 'AI assurance', strength: 'core' }] }],
  minimum_score: 3,
};

describe('profile JSON import', () => {
  it('accepts a standalone topic profile for the native save command', () => {
    expect(parseProfileJson(JSON.stringify(example))).toEqual(example);
  });

  it('rejects collections and the protected built-in profile', () => {
    expect(() => parseProfileJson(JSON.stringify({ schema_version: 1, profiles: [example] }))).toThrow('單一主題設定檔');
    expect(() => parseProfileJson(JSON.stringify({ ...example, profile_id: 'uk-tech-law' }))).toThrow('不可覆寫');
  });

  it('reports invalid JSON and missing required fields', () => {
    expect(() => parseProfileJson('{')).toThrow('JSON 格式錯誤');
    expect(() => parseProfileJson(JSON.stringify({ profile_id: 'sample' }))).toThrow('必要欄位');
  });
});
