export function defaultPeriod(today: Date, days = 14) {
  const end = new Date(today);
  const start = new Date(today);
  start.setDate(start.getDate() - Math.max(days - 1, 0));
  const iso = (value: Date) => value.toISOString().slice(0, 10);
  return { since: iso(start), until: iso(end) };
}
