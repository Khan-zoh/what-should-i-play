export const RATING_OPTIONS = [
  { label: "Loved", value: 5 },
  { label: "Liked", value: 4 },
  { label: "Meh", value: 3 },
  { label: "Disliked", value: 2 },
  { label: "Hated", value: 1 },
] as const;

export type RatingValue = 1 | 2 | 3 | 4 | 5;

export function labelForValue(value: number | null): string {
  if (value === null) return "Haven't played";
  return RATING_OPTIONS.find((o) => o.value === value)?.label ?? "Haven't played";
}

export const STATUS_OPTIONS = [
  { label: "Backlog", value: "backlog" },
  { label: "Installed", value: "installed" },
  { label: "Currently playing", value: "currently_playing" },
  { label: "Completed", value: "completed" },
  { label: "Abandoned", value: "abandoned" },
] as const;

export function labelForStatus(status: string | null): string {
  if (status === null) return "No status";
  return STATUS_OPTIONS.find((o) => o.value === status)?.label ?? status;
}
