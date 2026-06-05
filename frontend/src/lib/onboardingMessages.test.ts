import { describe, expect, it } from "vitest";
import { messageForErrorCode } from "@/lib/onboardingMessages";

describe("messageForErrorCode", () => {
  it("offers ID re-entry only for invalid_steamid", () => {
    expect(messageForErrorCode("invalid_steamid").allowIdReentry).toBe(true);
    expect(messageForErrorCode("private_profile").allowIdReentry).toBe(false);
    expect(messageForErrorCode("rate_limited").allowIdReentry).toBe(false);
    expect(messageForErrorCode("steam_auth").allowIdReentry).toBe(false);
  });

  it("gives a distinct title per known code", () => {
    const titles = [
      "private_profile",
      "invalid_steamid",
      "rate_limited",
      "steam_auth",
    ].map((c) => messageForErrorCode(c).title);
    expect(new Set(titles).size).toBe(4);
  });

  it("falls back for unknown or null codes", () => {
    expect(messageForErrorCode(null).title).toBe("Import failed");
    expect(messageForErrorCode("weird_code").title).toBe("Import failed");
  });
});
