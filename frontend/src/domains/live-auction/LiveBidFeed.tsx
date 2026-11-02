import React from "react";
import type { LotWsEvent } from "../../shared/types/domain";
import { ReticleFrame } from "../../shared/ui/BrandGlyphs";

export interface LiveBidFeedProps {
  events: ReadonlyArray<LotWsEvent>;
  currentLeaderId?: string | null | undefined;
}

function formatEventTimestamp(isoString: string): string {
  try {
    const d = new Date(isoString);
    return d.toISOString().slice(11, 19) + " UTC";
  } catch {
    return isoString;
  }
}

export const LiveBidFeed: React.FC<LiveBidFeedProps> = ({
  events,
  currentLeaderId,
}) => {
  const visibleEvents = events.filter((e) => e.event_type !== "LOT_SNAPSHOT");

  return (
    <div
      data-testid="live-bid-feed"
      className="rounded-none border border-[#262626] bg-[#141414] flex flex-col"
    >
      <div className="border-b border-[#262626] px-4 py-2.5 text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6] flex items-center justify-between">
        <span>LIVE AUDIT TRAIL / STREAM</span>
        <span className="text-[#F5F5F5]">
          [{visibleEvents.length} {visibleEvents.length === 1 ? "ENTRY" : "ENTRIES"}]
        </span>
      </div>

      <div className="max-h-[340px] overflow-y-auto divide-y divide-[#262626]">
        {visibleEvents.length === 0 ? (
          <div className="px-4 py-8 text-center text-xs font-mono-tech uppercase text-[#525252]">
            NO LIVE BIDDING ACTIVITY YET
          </div>
        ) : (
          visibleEvents.map((evt) => {
            switch (evt.event_type) {
              case "BID_PLACED":
                return (
                  <div
                    key={evt.bid_id}
                    data-testid="bid-feed-item-bid"
                    className="flex items-center justify-between gap-3 px-4 py-2.5 text-xs font-mono-tech hover:bg-[#262626]/40 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <ReticleFrame
                        size="sm"
                        bracketColor="#F5F5F5"
                        className="px-1.5 py-0.5 text-[10px] font-bold uppercase text-[#F5F5F5]"
                      >
                        <span>BID</span>
                      </ReticleFrame>
                      <span className="font-bold text-[#F5F5F5]">
                        ${evt.amount}
                      </span>
                      <span className="text-[#A6A6A6]">
                        BY {evt.leader_username_masked}
                      </span>
                      {currentLeaderId !== undefined &&
                        currentLeaderId !== null &&
                        evt.leader_user_id === currentLeaderId && (
                          <span
                            data-testid="bid-feed-leader-tag"
                            className="border border-[#F5F5F5] px-1 py-0.5 text-[9px] uppercase font-bold text-[#F5F5F5]"
                          >
                            HIGH BIDDER
                          </span>
                        )}
                      {evt.triggered_anti_snipe && (
                        <span className="bg-[#F5F5F5] text-[#141414] font-bold px-1.5 py-0.5 text-[10px] uppercase">
                          +2:00 EXTENDED
                        </span>
                      )}
                    </div>
                    <span className="text-[11px] text-[#525252]">
                      {formatEventTimestamp(evt.server_time)}
                    </span>
                  </div>
                );

              case "LOT_EXTENDED":
                return (
                  <div
                    key={`extended-${String(evt.anti_snipe_extensions_count)}-${evt.server_time}`}
                    data-testid="bid-feed-item-extended"
                    className="flex items-center justify-between gap-3 px-4 py-2 text-xs font-mono-tech bg-[#262626]/20"
                  >
                    <div className="flex items-center gap-2 text-[#F5F5F5]">
                      <span className="font-bold">LOT EXTENDED (+2:00)</span>
                      <span className="text-[#A6A6A6] text-[11px]">
                        [EXTENSION #{evt.anti_snipe_extensions_count}]
                      </span>
                    </div>
                    <span className="text-[11px] text-[#525252]">
                      {formatEventTimestamp(evt.server_time)}
                    </span>
                  </div>
                );

              case "LOT_SOLD":
                return (
                  <div
                    key={`sold-${evt.final_price}-${evt.server_time}`}
                    data-testid="bid-feed-item-sold"
                    className="flex items-center justify-between gap-3 px-4 py-2 text-xs font-mono-tech bg-[#D8D8D8] text-[#141414]"
                  >
                    <div className="flex items-center gap-2 font-bold uppercase">
                      <span>
                        LOT SOLD · ${evt.final_price}
                        {evt.via_buy_now ? " (VIA BUY NOW)" : ""}
                      </span>
                    </div>
                    <span className="text-[11px] text-[#525252]">
                      {formatEventTimestamp(evt.server_time)}
                    </span>
                  </div>
                );

              case "LOT_ENDED":
                return (
                  <div
                    key={`ended-${evt.status}-${evt.server_time}`}
                    data-testid="bid-feed-item-ended"
                    className="flex items-center justify-between gap-3 px-4 py-2 text-xs font-mono-tech bg-[#262626]/60 text-[#A6A6A6]"
                  >
                    <span className="uppercase">
                      {evt.status === "ENDED_WON"
                        ? `LOT CLOSED · ENDED_WON ($${evt.final_price})`
                        : `LOT CLOSED · ${evt.status}`}
                    </span>
                    <span className="text-[11px] text-[#525252]">
                      {formatEventTimestamp(evt.server_time)}
                    </span>
                  </div>
                );
            }
          })
        )}
      </div>
    </div>
  );
};
