import React, { useCallback, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import { getRemainingMs } from "../../shared/store/clockStore";
import { Badge } from "../../shared/ui/Badge";
import { CategorySpecsTable } from "../../shared/ui/CategorySpecsTable";
import { CountdownTimer } from "../../shared/ui/CountdownTimer";
import { MediaGallery } from "../../shared/ui/MediaGallery";
import { PriceTicker } from "../../shared/ui/PriceTicker";
import { SkeletonBox } from "../../shared/ui/SkeletonBox";
import type { LotDetail } from "../../shared/types/domain";
import { AntiSnipeAlert } from "./AntiSnipeAlert";
import { BidActionPanel } from "./BidActionPanel";
import { LiveBidFeed } from "./LiveBidFeed";
import { useLiveLotSocket } from "./useLiveLotSocket";

export const LiveLotPage: React.FC = () => {
  const { lotId } = useParams<{ lotId: string }>();

  const {
    lot,
    recentEvents,
    isAntiSnipeExtended,
    dismissAntiSnipeAlert,
    isLoading,
    error,
    refreshLot,
  } = useLiveLotSocket(lotId ?? "");

  const lotRef = useRef(lot);
  lotRef.current = lot;

  const expiredEndsAtRef = useRef<string | null>(null);
  const prevLotIdRef = useRef<string | undefined>(lotId);
  const prevLotRef = useRef<LotDetail | null>(null);

  if (prevLotIdRef.current !== lotId) {
    prevLotIdRef.current = lotId;
    prevLotRef.current = null;
    expiredEndsAtRef.current = null;
  }

  if (lot !== null && prevLotRef.current !== lot) {
    prevLotRef.current = lot;
    const remaining = getRemainingMs(lot.ends_at);
    if (remaining === 0 && expiredEndsAtRef.current === null) {
      expiredEndsAtRef.current = lot.ends_at;
    } else if (remaining > 0) {
      expiredEndsAtRef.current = null;
    }
  }

  const handleExpire = useCallback(() => {
    const currentLot = lotRef.current;
    if (currentLot === null || currentLot.status !== "LIVE") {
      return;
    }
    if (expiredEndsAtRef.current === currentLot.ends_at) {
      return;
    }
    expiredEndsAtRef.current = currentLot.ends_at;
    void refreshLot();
  }, [refreshLot]);

  const handleBidSuccess = useCallback(() => {
    void refreshLot();
  }, [refreshLot]);

  const handleBuyNowSuccess = useCallback(() => {
    void refreshLot();
  }, [refreshLot]);

  if (isLoading && lot === null) {
    return (
      <div
        data-testid="live-lot-loading"
        className="flex flex-col gap-6 font-mono-tech"
      >
        <div className="flex flex-col gap-2">
          <SkeletonBox className="h-6 w-44" />
          <SkeletonBox className="h-10 w-3/5" />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <div className="lg:col-span-7 flex flex-col gap-4">
            <SkeletonBox className="h-[480px] w-full" />
            <SkeletonBox className="h-[240px] w-full" />
          </div>
          <div className="lg:col-span-5 flex flex-col gap-4">
            <SkeletonBox className="h-20 w-full" />
            <SkeletonBox className="h-28 w-full" />
            <SkeletonBox className="h-[300px] w-full" />
          </div>
        </div>
      </div>
    );
  }

  if (lot === null) {
    return (
      <div
        data-testid="live-lot-error"
        className="border border-[#262626] bg-[#141414] p-8 text-center font-mono-tech flex flex-col items-center gap-4"
      >
        <span className="text-sm uppercase text-[#A6A6A6]">
          {error ?? "ARCHIVAL LOT NOT FOUND"}
        </span>
        <Link
          to="/catalog"
          className="border border-[#F5F5F5] bg-[#F5F5F5] text-[#141414] px-4 py-2 text-xs font-bold uppercase"
        >
          RETURN TO CATALOG ↗
        </Link>
      </div>
    );
  }

  const statusTone =
    lot.status === "LIVE"
      ? "live"
      : lot.status === "ENDED_WON"
        ? "claimable"
        : "neutral";

  return (
    <div
      data-testid="live-lot-page"
      className="flex flex-col gap-6 font-mono-tech"
    >
      <AntiSnipeAlert
        isExtended={isAntiSnipeExtended}
        extensionsCount={lot.anti_snipe_extensions_count}
        onDismiss={dismissAntiSnipeAlert}
      />

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#262626] pb-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <Badge tone="neutral">{lot.category}</Badge>
            <Badge tone={statusTone}>{lot.status}</Badge>
            {lot.anti_snipe_extensions_count > 0 && (
              <Badge tone="live">
                EXTENDED x{lot.anti_snipe_extensions_count}
              </Badge>
            )}
          </div>
          <h1 className="text-2xl sm:text-3xl lg:text-4xl font-display font-black uppercase tracking-tight text-[#F5F5F5]">
            {lot.title}
          </h1>
          {lot.subtitle.length > 0 && (
            <p className="text-xs sm:text-sm text-[#A6A6A6] uppercase tracking-wider">
              {lot.subtitle}
            </p>
          )}
        </div>

        <div className="flex flex-col sm:items-end text-xs text-[#525252]">
          <span>LOT ID: {lot.id.slice(0, 13)}...</span>
          <span>BIDS LOGGED: {lot.bid_count}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        <div className="lg:col-span-7 flex flex-col gap-6">
          <MediaGallery media={lot.media} />

          <div className="rounded-none border border-[#262626] bg-[#141414] p-4 flex flex-col gap-2">
            <div className="border-b border-[#262626] pb-2 text-xs uppercase tracking-wider text-[#A6A6A6]">
              CURATORIAL PROVENANCE & CONDITION NOTES
            </div>
            <p className="text-xs text-[#D8D8D8] whitespace-pre-wrap leading-relaxed">
              {lot.description}
            </p>
          </div>

          <CategorySpecsTable specs={lot.specs} />
        </div>

        <div className="lg:col-span-5 flex flex-col gap-4 sticky top-24">
          <CountdownTimer
            endsAtIso={lot.ends_at}
            status={lot.status}
            antiSnipeExtensionsCount={lot.anti_snipe_extensions_count}
            onExpire={handleExpire}
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <PriceTicker
              amountUsd={lot.current_price}
              label={lot.bid_count > 0 ? "CURRENT LEADER" : "STARTING BID"}
              size="lg"
              highlightChange={true}
            />
            {lot.is_buy_now_available && lot.buy_now_price !== null && (
              <PriceTicker
                amountUsd={lot.buy_now_price}
                label="BUY NOW PRICE"
                size="lg"
              />
            )}
          </div>

          <BidActionPanel
            lot={lot}
            onBidSuccess={handleBidSuccess}
            onBuyNowSuccess={handleBuyNowSuccess}
          />

          <LiveBidFeed
            events={recentEvents}
            currentLeaderId={lot.leader_user_id}
          />
        </div>
      </div>
    </div>
  );
};
