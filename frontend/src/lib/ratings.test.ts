import { describe, expect, it } from "vitest";
import {
  RATING_OPTIONS,
  STATUS_OPTIONS,
  labelForStatus,
  labelForValue,
} from "@/lib/ratings";

describe("ratings mapping", () => {
  it("maps each value to its label", () => {
    expect(labelForValue(5)).toBe("Loved");
    expect(labelForValue(4)).toBe("Liked");
    expect(labelForValue(3)).toBe("Meh");
    expect(labelForValue(2)).toBe("Disliked");
    expect(labelForValue(1)).toBe("Hated");
  });

  it("treats null and unknown values as 'Haven't played'", () => {
    expect(labelForValue(null)).toBe("Haven't played");
    expect(labelForValue(99)).toBe("Haven't played");
  });

  it("covers exactly the five 1..5 values", () => {
    expect(RATING_OPTIONS.map((o) => o.value).sort()).toEqual([1, 2, 3, 4, 5]);
  });

  it("maps status values and falls back gracefully", () => {
    expect(labelForStatus("currently_playing")).toBe("Currently playing");
    expect(labelForStatus(null)).toBe("No status");
    expect(labelForStatus("unmapped")).toBe("unmapped");
  });

  it("status options are a subset of valid backend statuses", () => {
    const allowed = new Set([
      "backlog",
      "installed",
      "currently_playing",
      "completed",
      "abandoned",
    ]);
    for (const opt of STATUS_OPTIONS) expect(allowed.has(opt.value)).toBe(true);
  });
});
