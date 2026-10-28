import React from "react";
import { Link } from "react-router-dom";
import { getRemainingMs } from "../../shared/store/clockStore";
import type { LotDetail } from "../../shared/types/domain";
import { Badge } from "../../shared/ui/Badge";
import { ReticleFrame, SlashedZeroGlyph } from "../../shared/ui/BrandGlyphs";
import { CountdownTimer } from "../../shared/ui/CountdownTimer";
import { PriceTicker } from "../../shared/ui/PriceTicker";

export interface LotCardProps {
  lot: LotDetail;
  onSelectLot?: ((lotId: string) => void) | undefined;
}

export const LotCard: React.FC<LotCardProps> = ({ lot, onSelectLot }) => {
  const primaryMedia =
    lot.media.find((m) => m.slot_type === "PRIMARY") ?? lot.media[0];

  const statusTone =
    lot.status === "LIVE"
      ? "live"
      : lot.status === "ENDED_WON"
        ? "claimable"
        : "neutral";

  const remainingMs = getRemainingMs(lot.ends_at);
  const isEndingSoon =
    lot.status === "LIVE" &&
    remainingMs > 0 &&
    (remainingMs <= 24 * 60 * 60 * 1000 || lot.anti_snipe_extensions_count > 0);

  const displayPrice = lot.bid_count > 0 ? lot.current_price : lot.start_price;

  const handleClick = () => {
    if (onSelectLot !== undefined) {
      onSelectLot(lot.id);
    }
  };

  return (
    <article
      data-testid={`lot-card-${lot.id}`}
      className="group flex flex-col justify-between border border-[#262626] bg-[#141414] hover:border-[#F5F5F5] transition-colors"
    >
      <div>
        <div className="relative aspect-[4/3] w-full overflow-hidden bg-black border-b border-[#262626]">
          {primaryMedia !== undefined ? (
            <img
              src={primaryMedia.public_url}
              alt={lot.title}
              className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
            />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-[#525252]">
              <SlashedZeroGlyph className="w-10 h-12" />
              <span className="font-mono-tech text-[10px] tracking-widest uppercase">
                NO MEDIA RECORD
              </span>
            </div>
          )}

          <div className="absolute top-2 left-2 flex flex-wrap items-center gap-1.5 z-10">
            <Badge tone={statusTone}>
              {lot.status === "LIVE" ? "LIVE AUCTION" : lot.status}
            </Badge>
            {isEndingSoon && (
              <Badge tone="endingSoon">ENDING SOON</Badge>
            )}
            <Badge tone="category">[{lot.category}]</Badge>
          </div>

          {lot.is_buy_now_available && lot.buy_now_price !== null && (
            <div className="absolute bottom-2 right-2 z-10">
              <span className="bg-[#A6A6A6] text-[#141414] border border-[#F5F5F5] px-2 py-0.5 text-[10px] font-mono-tech font-bold uppercase tracking-wider">
                BUY NOW ${lot.buy_now_price}
              </span>
            </div>
          )}
        </div>

        <div className="p-4 flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Link
              to={`/lots/${lot.id}`}
              onClick={handleClick}
              className="text-sm font-mono-tech font-bold uppercase text-[#F5F5F5] hover:underline line-clamp-1"
            >
              {lot.title}
            </Link>
            <div className="text-xs font-sans text-[#A6A6A6] line-clamp-1">
              {lot.subtitle}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-[#262626]">
            <PriceTicker
              amountUsd={displayPrice}
              label={lot.bid_count > 0 ? "CURRENT BID" : "STARTING BID"}
              size="sm"
            />
            <div className="border border-[#262626] bg-[#141414] p-2 flex flex-col justify-between font-mono-tech text-right">
              <span className="text-[10px] uppercase text-[#A6A6A6] tracking-widest">
                ACTIVITY
              </span>
              <span className="text-sm font-bold text-[#F5F5F5]">
                {lot.bid_count} {lot.bid_count === 1 ? "BID" : "BIDS"}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="p-4 pt-0 flex flex-col gap-3">
        <CountdownTimer
          endsAtIso={lot.ends_at}
          status={lot.status}
          antiSnipeExtensionsCount={lot.anti_snipe_extensions_count}
        />

        <Link
          to={`/lots/${lot.id}`}
          onClick={handleClick}
          className="w-full rounded-none border border-[#262626] bg-[#141414] py-2 text-xs font-mono-tech uppercase tracking-wider text-[#F5F5F5] hover:border-[#F5F5F5] hover:bg-[#262626] transition-colors flex items-center justify-center gap-2"
        >
          <ReticleFrame size="sm" />
          <span>INSPECT LOT & PLACE BID</span>
        </Link>
      </div>
    </article>
  );
};
