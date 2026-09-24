export const workerChoices = Array.from({ length: 16 }, (_, index) => index + 1);

type ProfileWithId = { profile_id: string };

export function buildRunRequest<T extends ProfileWithId>(options: {
  since: string;
  until: string;
  output: string;
  workers: number;
  profile: T | null;
  calendar: string;
  selectedSources: string[];
  minimumScore: number;
}) {
  if (!Number.isInteger(options.workers) || options.workers < 1 || options.workers > 16) {
    throw new Error('併發抓取數必須介於 1 至 16');
  }
  return {
    since: options.since,
    until: options.until,
    output: options.output,
    workers: options.workers,
    profilePath: options.profile?.profile_id ?? null,
    calendar: options.calendar,
    selectedSources: options.selectedSources,
    minimumScore: options.minimumScore,
    profile: options.profile
      ? { ...options.profile, selected_sources: options.selectedSources, minimum_score: options.minimumScore }
      : null,
  };
}
