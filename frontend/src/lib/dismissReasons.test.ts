import { describe, expect, it } from "vitest";
import { DISMISS_REASONS } from "@/lib/dismissReasons";

describe("DISMISS_REASONS", () => {
  it("matches the backend's accepted reason values", () => {
    const values = DISMISS_REASONS.map((r) => r.value).sort();
    expect(values).toEqual(
      [
        "already_played_elsewhere",
        "not_interested",
        "too_expensive",
        "too_long",
        "wrong_genre",
        "wrong_platform",
      ].sort(),
    );
  });

  it("gives every reason a human label", () => {
    for (const r of DISMISS_REASONS) {
      expect(r.label.length).toBeGreaterThan(0);
    }
  });
});
