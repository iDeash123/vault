import { create } from "zustand";

export interface ClockState {
  clockOffsetMs: number;
  lastServerTimeIso: string | null;
  syncWithServerTime: (serverTimeIso: string) => void;
  getServerNowMs: () => number;
  getRemainingMs: (endsAtIso: string) => number;
  resetClockOffset: () => void;
}

export const useClockStore = create<ClockState>((set, get) => ({
  clockOffsetMs: 0,
  lastServerTimeIso: null,
  syncWithServerTime: (serverTimeIso: string) => {
    const parsedServerMs = Date.parse(serverTimeIso);
    if (Number.isNaN(parsedServerMs)) {
      throw new Error(`Invalid server_time ISO string: ${serverTimeIso}`);
    }
    const offsetMs = parsedServerMs - Date.now();
    set({
      clockOffsetMs: offsetMs,
      lastServerTimeIso: serverTimeIso,
    });
  },
  getServerNowMs: () => Date.now() + get().clockOffsetMs,
  getRemainingMs: (endsAtIso: string) => {
    const parsedEndsAtMs = Date.parse(endsAtIso);
    if (Number.isNaN(parsedEndsAtMs)) {
      throw new Error(`Invalid ends_at ISO string: ${endsAtIso}`);
    }
    const serverNowMs = Date.now() + get().clockOffsetMs;
    return Math.max(0, parsedEndsAtMs - serverNowMs);
  },
  resetClockOffset: () => {
    set({
      clockOffsetMs: 0,
      lastServerTimeIso: null,
    });
  },
}));

export function syncWithServerTime(serverTimeIso: string): void {
  useClockStore.getState().syncWithServerTime(serverTimeIso);
}

export function getServerNowMs(): number {
  return useClockStore.getState().getServerNowMs();
}

export function getRemainingMs(endsAtIso: string): number {
  return useClockStore.getState().getRemainingMs(endsAtIso);
}

export function getClockOffsetMs(): number {
  return useClockStore.getState().clockOffsetMs;
}

export function resetClockOffset(): void {
  useClockStore.getState().resetClockOffset();
}
