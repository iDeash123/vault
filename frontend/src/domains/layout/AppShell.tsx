import React, { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiClient } from "../../shared/api/client";
import { useAuthStore } from "../../shared/store/authStore";
import { useClockStore } from "../../shared/store/clockStore";
import { ReticleFrame, UnborderedWord } from "../../shared/ui/BrandGlyphs";
import { ClaimableHoldsBanner } from "../../shared/ui/ClaimableHoldsBanner";
import { NAV_ITEMS } from "./navConfig";

const ASYMMETRIC_18_GUIDES: ReadonlyArray<number> = [
  3.5, 5.5, 4.5, 6.5, 8.0, 5.0, 4.0, 7.5, 5.5, 5.5, 7.5, 4.0, 5.0, 8.0, 6.5,
  4.5, 5.5, 3.5,
];

export interface AppShellProps {
  children: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const claimableCount = useAuthStore((state) => state.claimableCount);
  const updateBalances = useAuthStore((state) => state.updateBalances);
  const setClaimableCount = useAuthStore((state) => state.setClaimableCount);
  const clockOffsetMs = useClockStore((state) => state.clockOffsetMs);
  const [showGridOverlay, setShowGridOverlay] = useState<boolean>(false);
  const [isClaimingAll, setIsClaimingAll] = useState<boolean>(false);

  const visibleNavItems = NAV_ITEMS.filter((item) => {
    if (item.allowedRoles !== undefined) {
      return user !== null && item.allowedRoles.includes(user.role);
    }
    return true;
  });

  const handleGlobalClaimAll = async () => {
    if (user === null) {
      return;
    }
    setIsClaimingAll(true);
    try {
      const result = await apiClient.post<{
        available_balance: string;
        held_balance: string;
        claimable_balance: string;
      }>("/wallet/claims/claim-all");
      updateBalances({
        available_balance: result.available_balance,
        held_balance: result.held_balance,
        claimable_balance: result.claimable_balance,
      });
      setClaimableCount(0);
    } finally {
      setIsClaimingAll(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#141414] text-[#F5F5F5] flex flex-col relative">
      {showGridOverlay && (
        <div
          aria-hidden="true"
          className="fixed inset-0 pointer-events-none z-40 flex"
        >
          {ASYMMETRIC_18_GUIDES.map((widthPct, idx) => (
            <div
              key={idx}
              style={{ width: `${String(widthPct)}%` }}
              className="h-full border-r border-[#262626]/60"
            />
          ))}
        </div>
      )}

      {user !== null && (
        <ClaimableHoldsBanner
          claimableBalance={user.claimable_balance}
          claimableCount={
            claimableCount > 0
              ? claimableCount
              : Number(user.claimable_balance) > 0
                ? 1
                : 0
          }
          onClaimAll={handleGlobalClaimAll}
          isClaiming={isClaimingAll}
        />
      )}

      <header className="border-b border-[#262626] bg-[#141414] sticky top-0 z-30">
        <div className="mx-auto max-w-[1360px] px-6 py-4 flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#262626] pb-3">
            <Link
              to="/catalog"
              className="text-2xl md:text-3xl font-display font-black uppercase tracking-[-0.045em] text-[#F5F5F5]"
            >
              <UnborderedWord word="ØBSØLETE" cutoutColor="#141414" />
            </Link>

            <div className="flex flex-wrap items-center gap-3 text-xs font-mono-tech">
              <span className="border border-[#262626] px-2.5 py-1 text-[#A6A6A6]">
                SYNC OFFSET: {clockOffsetMs >= 0 ? `+${String(clockOffsetMs)}` : String(clockOffsetMs)}ms
              </span>
              <button
                type="button"
                onClick={() => {
                  setShowGridOverlay((prev) => !prev);
                }}
                className={`rounded-none border px-2.5 py-1 uppercase ${
                  showGridOverlay
                    ? "border-[#F5F5F5] bg-[#F5F5F5] text-[#141414] font-semibold"
                    : "border-[#262626] bg-[#141414] text-[#A6A6A6] hover:border-[#F5F5F5]"
                }`}
              >
                #18GUIDES
              </button>
              {user !== null ? (
                <div className="flex items-center gap-2 border border-[#262626] px-3 py-1 bg-[#141414]">
                  <span className="text-[#A6A6A6] uppercase">
                    @{user.username}
                  </span>
                  <span className="text-[#F5F5F5] font-bold">
                    AVAIL: ${user.available_balance}
                  </span>
                  {Number(user.claimable_balance) > 0 && (
                    <span className="bg-[#D8D8D8] text-[#141414] px-1.5 py-0.5 font-bold">
                      CLAIMABLE: ${user.claimable_balance}
                    </span>
                  )}
                </div>
              ) : (
                <Link
                  to="/login"
                  className="border border-[#F5F5F5] bg-[#F5F5F5] text-[#141414] px-3 py-1 font-bold uppercase"
                >
                  AUTHENTICATE
                </Link>
              )}
            </div>
          </div>

          <nav
            aria-label="Primary Archival Navigation"
            className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2"
          >
            {visibleNavItems.map((item) => {
              const isActive =
                location.pathname === item.path ||
                location.pathname.startsWith(`${item.path}/`);
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`border px-3 py-2 transition-colors ${
                    isActive
                      ? "border-[#F5F5F5] bg-[#141414] text-[#F5F5F5]"
                      : "border-[#262626] bg-[#141414] text-[#A6A6A6] hover:border-[#F5F5F5] hover:text-[#F5F5F5]"
                  }`}
                >
                  <ReticleFrame
                    size="sm"
                    bracketColor={isActive ? "#F5F5F5" : "transparent"}
                    className="w-full justify-start"
                  >
                    <div className="flex flex-col text-left">
                      <span className="text-[10px] font-mono-tech text-[#525252]">
                        {item.indexCode} / {item.subLabel}
                      </span>
                      <span className="text-xs font-mono-tech font-bold uppercase tracking-wider">
                        {item.label} ↗
                      </span>
                    </div>
                  </ReticleFrame>
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-[1360px] px-6 py-8">
        {children}
      </main>

      <footer className="border-t border-[#262626] bg-[#141414] py-6">
        <div className="mx-auto max-w-[1360px] px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs font-mono-tech text-[#525252] uppercase">
          <span>ØBSØLETE ARCHIVAL VAULT · ZERO ROUNDED CORNERS (0PX)</span>
          <span>FOUNDATION SCHEMA FIRST · DOUBLE-ENTRY LEDGER</span>
        </div>
      </footer>
    </div>
  );
};
