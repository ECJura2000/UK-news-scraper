export type TimeSync = { source: string; server?: string; utc: string; checked_at?: string; offset_seconds?: number | null; round_trip_seconds?: number | null; warning?: string };
export type ClockSnapshot = { state: TimeSync; anchoredAt: number };
export function clockDate(snapshot?: ClockSnapshot, monotonicNow = performance.now()): Date {
  if (!snapshot || !Number.isFinite(Date.parse(snapshot.state.utc))) return new Date();
  return new Date(Date.parse(snapshot.state.utc) + Math.max(0, monotonicNow - snapshot.anchoredAt));
}
export function timeSourceLabel(state?: TimeSync): string {
  if (!state) return '正在連接國家標準時間…';
  return state.source === 'ntp' ? `國家標準時間 · ${state.server}` : `使用本機時間：${state.warning || 'NTP 尚未校正'}`;
}

export function headerTime(snapshot?: ClockSnapshot, monotonicNow = performance.now()): { date: string; label: string } {
  const date = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit' }).format(clockDate(snapshot, monotonicNow));
  const valid = snapshot && Number.isFinite(Date.parse(snapshot.state.utc));
  return { date, label: valid && snapshot.state.source === 'ntp' ? '國家標準時間' : snapshot ? '本機時間' : '校時中' };
}
