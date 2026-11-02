import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "../../shared/api/client";
import {
  connectLotStream,
  connectUserNotificationsStream,
} from "../../shared/api/wsClient";
import { useAuthStore } from "../../shared/store/authStore";
import { syncWithServerTime } from "../../shared/store/clockStore";
import type {
  BidPlacedEvent,
  LotDetail,
  LotWsEvent,
  UserNotificationWsEvent,
} from "../../shared/types/domain";

export interface UseLiveLotSocketOptions {
  initialLot?: LotDetail | null | undefined;
  enabled?: boolean | undefined;
  onEvent?: ((event: LotWsEvent) => void) | undefined;
}

export interface UseLiveLotSocketResult {
  lot: LotDetail | null;
  setLot: React.Dispatch<React.SetStateAction<LotDetail | null>>;
  recentEvents: LotWsEvent[];
  lastEvent: LotWsEvent | null;
  isConnected: boolean;
  isAntiSnipeExtended: boolean;
  dismissAntiSnipeAlert: () => void;
  refreshLot: () => Promise<void>;
  isLoading: boolean;
  error: string | null;
}

export function applyLotWsEvent(
  currentLot: LotDetail | null,
  event: LotWsEvent,
): LotDetail | null {
  if (currentLot === null) {
    return null;
  }

  switch (event.event_type) {
    case "LOT_SNAPSHOT":
      return {
        ...currentLot,
        status: event.status,
        current_price: event.current_price,
        min_valid_bid: event.min_valid_bid,
        bid_count: event.bid_count,
        leader_user_id: event.leader_user_id,
        is_buy_now_available: event.is_buy_now_available,
        is_reserve_met: event.is_reserve_met,
        ends_at: event.ends_at,
        anti_snipe_extensions_count: event.anti_snipe_extensions_count,
        server_time: event.server_time,
      };

    case "BID_PLACED":
      return {
        ...currentLot,
        current_price: event.amount,
        min_valid_bid: event.min_valid_bid,
        bid_count: event.bid_count,
        leader_user_id: event.leader_user_id,
        is_buy_now_available: event.is_buy_now_available,
        is_reserve_met: event.is_reserve_met,
        ends_at: event.ends_at,
        anti_snipe_extensions_count: event.triggered_anti_snipe
          ? Math.max(
              currentLot.anti_snipe_extensions_count + 1,
              currentLot.anti_snipe_extensions_count,
            )
          : currentLot.anti_snipe_extensions_count,
        server_time: event.server_time,
      };

    case "LOT_EXTENDED":
      return {
        ...currentLot,
        ends_at: event.new_ends_at,
        anti_snipe_extensions_count: Math.max(
          currentLot.anti_snipe_extensions_count,
          event.anti_snipe_extensions_count,
        ),
        server_time: event.server_time,
      };

    case "LOT_SOLD":
      return {
        ...currentLot,
        status: "ENDED_WON",
        current_price: event.final_price,
        leader_user_id: event.winner_user_id,
        is_buy_now_available: false,
        server_time: event.server_time,
      };

    case "LOT_ENDED":
      return {
        ...currentLot,
        status: event.status,
        current_price: event.final_price,
        leader_user_id: event.winner_user_id,
        is_buy_now_available: false,
        server_time: event.server_time,
      };
  }
}

function extractBidEvents(lotData: unknown): LotWsEvent[] {
  if (typeof lotData !== "object" || lotData === null) {
    return [];
  }
  const obj = lotData as Record<string, unknown>;
  if (!Array.isArray(obj.bids)) {
    return [];
  }
  const lotId = typeof obj.id === "string" ? obj.id : "";
  const minValidBid =
    typeof obj.min_valid_bid === "string" ? obj.min_valid_bid : "0.00";
  const bidCount = typeof obj.bid_count === "number" ? obj.bid_count : 0;
  const isBuyNowAvailable = Boolean(obj.is_buy_now_available);
  const isReserveMet = Boolean(obj.is_reserve_met);
  const endsAt = typeof obj.ends_at === "string" ? obj.ends_at : "";

  const bidEvents: BidPlacedEvent[] = [];
  for (const item of obj.bids) {
    if (typeof item === "object" && item !== null) {
      const b = item as Record<string, unknown>;
      if (
        typeof b.id === "string" &&
        typeof b.bidder_id === "string" &&
        typeof b.bidder_username_masked === "string" &&
        (typeof b.amount === "string" || typeof b.amount === "number") &&
        typeof b.created_at === "string"
      ) {
        const num = Number(b.amount);
        const formattedAmount = Number.isNaN(num)
          ? String(b.amount)
          : num.toFixed(2);
        bidEvents.push({
          event_type: "BID_PLACED",
          lot_id: lotId,
          bid_id: b.id,
          amount: formattedAmount,
          min_valid_bid: minValidBid,
          bid_count: bidCount,
          leader_user_id: b.bidder_id,
          leader_username_masked: b.bidder_username_masked,
          is_buy_now_available: isBuyNowAvailable,
          is_reserve_met: isReserveMet,
          ends_at: endsAt,
          triggered_anti_snipe: Boolean(b.triggered_anti_snipe),
          server_time: b.created_at,
        });
      }
    }
  }

  bidEvents.sort((a, b) => {
    const timeA = Date.parse(a.server_time);
    const timeB = Date.parse(b.server_time);
    if (!Number.isNaN(timeA) && !Number.isNaN(timeB) && timeA !== timeB) {
      return timeB - timeA;
    }
    return Number(b.amount) - Number(a.amount);
  });

  return bidEvents;
}

function mergeBidEvents(
  existingEvents: ReadonlyArray<LotWsEvent>,
  incomingEvents: ReadonlyArray<LotWsEvent>,
): LotWsEvent[] {
  const seenBidIds = new Set<string>();
  const merged: LotWsEvent[] = [];

  for (const evt of existingEvents) {
    if (evt.event_type === "BID_PLACED") {
      if (seenBidIds.has(evt.bid_id)) {
        continue;
      }
      seenBidIds.add(evt.bid_id);
    }
    merged.push(evt);
  }

  for (const evt of incomingEvents) {
    if (evt.event_type === "BID_PLACED") {
      if (seenBidIds.has(evt.bid_id)) {
        continue;
      }
      seenBidIds.add(evt.bid_id);
    }
    merged.push(evt);
  }

  merged.sort((a, b) => {
    const timeA = Date.parse(a.server_time);
    const timeB = Date.parse(b.server_time);
    if (!Number.isNaN(timeA) && !Number.isNaN(timeB) && timeA !== timeB) {
      return timeB - timeA;
    }
    if (a.event_type === "BID_PLACED" && b.event_type === "BID_PLACED") {
      return Number(b.amount) - Number(a.amount);
    }
    return 0;
  });

  return merged.slice(0, 50);
}

export function useLiveLotSocket(
  lotId: string,
  options?: UseLiveLotSocketOptions,
): UseLiveLotSocketResult {
  const initialLot = options?.initialLot;
  const [lot, setLot] = useState<LotDetail | null>(initialLot ?? null);
  const [recentEvents, setRecentEvents] = useState<LotWsEvent[]>(() =>
    options?.initialLot ? extractBidEvents(options.initialLot) : [],
  );
  const [lastEvent, setLastEvent] = useState<LotWsEvent | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isAntiSnipeExtended, setIsAntiSnipeExtended] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(
    initialLot === undefined || initialLot === null,
  );
  const [error, setError] = useState<string | null>(null);

  const onEventRef = useRef(options?.onEvent);
  onEventRef.current = options?.onEvent;
  const eventHistoryRef = useRef<LotWsEvent[]>([]);

  const refreshLot = useCallback(async () => {
    if (lotId.length === 0) {
      return;
    }
    setError(null);
    try {
      const freshLot = await apiClient.get<LotDetail>(`/lots/${lotId}`);
      let resolvedLot = freshLot;
      for (const evt of eventHistoryRef.current) {
        if (Date.parse(evt.server_time) >= Date.parse(freshLot.server_time)) {
          const applied = applyLotWsEvent(resolvedLot, evt);
          if (applied !== null) {
            resolvedLot = applied;
          }
        }
      }
      const historicalBidEvents = extractBidEvents(freshLot);
      if (historicalBidEvents.length > 0) {
        setRecentEvents((prev) => mergeBidEvents(prev, historicalBidEvents));
      }
      setLot((prev) => {
        if (prev === null) {
          return resolvedLot;
        }
        if (Date.parse(prev.server_time) > Date.parse(resolvedLot.server_time)) {
          return prev;
        }
        return resolvedLot;
      });
      if (resolvedLot.server_time.length > 0) {
        syncWithServerTime(resolvedLot.server_time);
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to fetch lot details.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [lotId]);

  useEffect(() => {
    eventHistoryRef.current = [];
    if (options?.initialLot) {
      setLot(options.initialLot);
      const initialBidEvents = extractBidEvents(options.initialLot);
      setRecentEvents(initialBidEvents);
      if (options.initialLot.server_time.length > 0) {
        syncWithServerTime(options.initialLot.server_time);
      }
      setIsLoading(false);
    } else {
      setLot(null);
      setRecentEvents([]);
      setIsLoading(true);
      void refreshLot();
    }
  }, [lotId, options?.initialLot, refreshLot]);

  useEffect(() => {
    if (options?.enabled === false || lotId.length === 0) {
      setIsConnected(false);
      return;
    }

    const socket = connectLotStream(
      lotId,
      (event: LotWsEvent) => {
        eventHistoryRef.current.push(event);
        if (eventHistoryRef.current.length > 100) {
          eventHistoryRef.current.splice(
            0,
            eventHistoryRef.current.length - 100,
          );
        }
        syncWithServerTime(event.server_time);
        setLot((prev) => applyLotWsEvent(prev, event));
        setLastEvent(event);
        if (event.event_type !== "LOT_SNAPSHOT") {
          setRecentEvents((prev) => {
            if (
              event.event_type === "BID_PLACED" &&
              prev.some(
                (e) =>
                  e.event_type === "BID_PLACED" && e.bid_id === event.bid_id,
              )
            ) {
              return prev;
            }
            return [event, ...prev].slice(0, 50);
          });
        }

        if (
          event.event_type === "LOT_EXTENDED" ||
          (event.event_type === "BID_PLACED" && event.triggered_anti_snipe)
        ) {
          setIsAntiSnipeExtended(true);
        }

        onEventRef.current?.(event);
      },
      {
        onOpen: () => {
          setIsConnected(true);
        },
        onClose: () => {
          setIsConnected(false);
        },
        onError: () => {
          setIsConnected(false);
        },
      },
    );

    return () => {
      socket.close();
      setIsConnected(false);
    };
  }, [lotId, options?.enabled]);

  const dismissAntiSnipeAlert = useCallback(() => {
    setIsAntiSnipeExtended(false);
  }, []);

  return {
    lot,
    setLot,
    recentEvents,
    lastEvent,
    isConnected,
    isAntiSnipeExtended,
    dismissAntiSnipeAlert,
    refreshLot,
    isLoading,
    error,
  };
}

export function useUserNotificationsSocket(options?: {
  onEvent?: ((event: UserNotificationWsEvent) => void) | undefined;
}): {
  isConnected: boolean;
} {
  const userId = useAuthStore((state) => state.user?.id);
  const accessToken = useAuthStore((state) => state.accessToken);
  const [isConnected, setIsConnected] = useState<boolean>(false);

  const onEventRef = useRef(options?.onEvent);
  onEventRef.current = options?.onEvent;

  useEffect(() => {
    if (accessToken === null || userId === undefined) {
      setIsConnected(false);
      return;
    }

    const socket = connectUserNotificationsStream(
      accessToken,
      (event: UserNotificationWsEvent) => {
        syncWithServerTime(event.server_time);

        if (event.event_type === "HOLD_BECAME_CLAIMABLE") {
          const state = useAuthStore.getState();
          const currentHeld =
            state.user !== null ? Number(state.user.held_balance) : 0;
          const outbidAmount = Number(event.amount);
          const nextHeld =
            Number.isNaN(currentHeld) || Number.isNaN(outbidAmount)
              ? state.user?.held_balance
              : Math.max(0, currentHeld - outbidAmount).toFixed(2);

          state.updateBalances({
            held_balance: nextHeld,
            claimable_balance: event.new_claimable_balance,
          });
          state.setClaimableCount(state.claimableCount + 1);
        }

        onEventRef.current?.(event);
      },
      false,
      {
        onOpen: () => {
          setIsConnected(true);
        },
        onClose: () => {
          setIsConnected(false);
        },
        onError: () => {
          setIsConnected(false);
        },
      },
    );

    return () => {
      socket.close();
      setIsConnected(false);
    };
  }, [accessToken, userId]);

  return { isConnected };
}
