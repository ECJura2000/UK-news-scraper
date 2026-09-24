export type Keyword = { phrase: string; strength: string };
export type Profile = {
  profile_id: string;
  name: string;
  description: string;
  version: number;
  selected_sources: string[];
  topics: { name: string; keywords: Keyword[] }[];
  minimum_score: number;
};

export function parseProfileJson(text: string): Profile {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new Error('JSON 格式錯誤，請檢查檔案內容');
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('請選擇單一主題設定檔 JSON');
  }
  const profile = value as Record<string, unknown>;
  if ('profiles' in profile) {
    throw new Error('請匯入單一主題設定檔，不要匯入 profiles.json 集合檔');
  }
  if (
    typeof profile.profile_id !== 'string' ||
    typeof profile.name !== 'string' ||
    profile.version !== 1 ||
    !Array.isArray(profile.selected_sources) ||
    !Array.isArray(profile.topics)
  ) {
    throw new Error('主題設定檔缺少必要欄位，請參照範例 JSON');
  }
  if (profile.profile_id === 'uk-tech-law') {
    throw new Error('內建 UK 科技法制設定不可覆寫，請先修改 profile_id');
  }
  return profile as Profile;
}
