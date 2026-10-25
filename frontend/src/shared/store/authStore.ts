import { create } from "zustand";
import type { UserProfile } from "../types/domain";

export interface BalanceUpdatePayload {
  available_balance?: string | undefined;
  held_balance?: string | undefined;
  claimable_balance?: string | undefined;
}

export interface AuthState {
  accessToken: string | null;
  user: UserProfile | null;
  isAuthenticated: boolean;
  claimableCount: number;
  setSession: (accessToken: string, user: UserProfile) => void;
  setAccessToken: (accessToken: string | null) => void;
  setUser: (user: UserProfile | null) => void;
  setClaimableCount: (count: number) => void;
  updateBalances: (balances: BalanceUpdatePayload) => void;
  clearSession: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  isAuthenticated: false,
  claimableCount: 0,
  setSession: (accessToken: string, user: UserProfile) => {
    set({
      accessToken,
      user,
      isAuthenticated: true,
    });
  },
  setAccessToken: (accessToken: string | null) => {
    set((state) => ({
      accessToken,
      isAuthenticated: accessToken !== null && state.user !== null,
    }));
  },
  setUser: (user: UserProfile | null) => {
    set((state) => ({
      user,
      isAuthenticated: state.accessToken !== null && user !== null,
    }));
  },
  setClaimableCount: (count: number) => {
    set({ claimableCount: Math.max(0, count) });
  },
  updateBalances: (balances: BalanceUpdatePayload) => {
    set((state) => {
      if (state.user === null) {
        return state;
      }
      return {
        user: {
          ...state.user,
          available_balance:
            balances.available_balance ?? state.user.available_balance,
          held_balance: balances.held_balance ?? state.user.held_balance,
          claimable_balance:
            balances.claimable_balance ?? state.user.claimable_balance,
        },
      };
    });
  },
  clearSession: () => {
    set({
      accessToken: null,
      user: null,
      isAuthenticated: false,
      claimableCount: 0,
    });
  },
}));
