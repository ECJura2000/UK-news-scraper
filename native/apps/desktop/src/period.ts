export function defaultPeriod(today: Date, days = 14) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(today);
  const value = (name: string) => parts.find(part => part.type === name)?.value ?? '';
  const end = new Date(`${value('year')}-${value('month')}-${value('day')}T00:00:00Z`);
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - Math.max(days, 0));
  const iso = (date: Date) => date.toISOString().slice(0, 10);
  return { since: iso(start), until: iso(end) };
}
