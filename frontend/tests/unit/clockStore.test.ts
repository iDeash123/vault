import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getClockOffsetMs,
  getRemainingMs,
  getServerNowMs,
  resetClockOffset,
  syncWithServerTime,
} from "../../src/shared/store/clockStore";

describe("clockStore server time synchronization", () => {
  const authoritativeServerTimeIso = "2026-10-25T15:00:00.000Z";
  const authoritativeServerTimeMs = Date.parse(authoritativeServerTimeIso);
  const lotEndsAtIso = "2026-10-25T15:02:00.000Z";
  const expectedRemainingMs = 120_000;

  beforeEach(() => {
    resetClockOffset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    resetClockOffset();
  });

  it("compensates when client clock lags behind server by 45_000 ms", () => {
    let fakeClientNowMs = authoritativeServerTimeMs - 45_000;
    vi.spyOn(Date, "now").mockImplementation(() => fakeClientNowMs);

    syncWithServerTime(authoritativeServerTimeIso);

    expect(getClockOffsetMs()).toBe(45_000);
    expect(getServerNowMs()).toBe(authoritativeServerTimeMs);
    expect(getRemainingMs(lotEndsAtIso)).toBe(expectedRemainingMs);

    fakeClientNowMs += 19_250;
    expect(getServerNowMs()).toBe(authoritativeServerTimeMs + 19_250);
    expect(getRemainingMs(lotEndsAtIso)).toBe(expectedRemainingMs - 19_250);
  });

  it("compensates when client clock is ahead of server by 45_000 ms", () => {
    let fakeClientNowMs = authoritativeServerTimeMs + 45_000;
    vi.spyOn(Date, "now").mockImplementation(() => fakeClientNowMs);

    syncWithServerTime(authoritativeServerTimeIso);

    expect(getClockOffsetMs()).toBe(-45_000);
    expect(getServerNowMs()).toBe(authoritativeServerTimeMs);
    expect(getRemainingMs(lotEndsAtIso)).toBe(expectedRemainingMs);

    fakeClientNowMs += 120_500;
    expect(getRemainingMs(lotEndsAtIso)).toBe(0);
  });

  it("throws on malformed ISO timestamp strings", () => {
    expect(() => {
      syncWithServerTime("not-a-timestamp");
    }).toThrowError("Invalid server_time ISO string");
    expect(() => {
      getRemainingMs("not-a-timestamp");
    }).toThrowError("Invalid ends_at ISO string");
  });
});
