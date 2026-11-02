import { act, cleanup, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../../src/shared/api/client";
import { buildWsUrl } from "../../src/shared/api/wsClient";
import { useAuthStore } from "../../src/shared/store/authStore";
import { getClockOffsetMs } from "../../src/shared/store/clockStore";
import type { LotDetail, UserProfile } from "../../src/shared/types/domain";
import { AppShell } from "../../src/domains/layout/AppShell";
import {
  applyLotWsEvent,
  useLiveLotSocket,
  useUserNotificationsSocket,
} from "../../src/domains/live-auction/useLiveLotSocket";

class MockWebSocket {
  public static instances: MockWebSocket[] = [];
  public url: string;
  public readyState: number = 1;
  public onopen: (() => void) | null = null;
  public onclose: (() => void) | null = null;
  public onerror: ((error: Event) => void) | null = null;
  public onmessage: ((event: MessageEvent<string>) => void) | null = null;

  public constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    setTimeout(() => {
      this.onopen?.();
    }, 0);
  }

  public send(_data: string): void {}

  public close(): void {
    this.readyState = 3;
    this.onclose?.();
  }

  public emit(data: Record<string, unknown>): void {
    const raw = JSON.stringify(data);
    this.onmessage?.(new MessageEvent("message", { data: raw }));
  }
}

const mockBaseLot: LotDetail = {
  id: "00000000-0000-0000-0000-000000000001",
  seller_id: "00000000-0000-0000-0000-000000000002",
  leader_user_id: null,
  category: "APPAREL",
  status: "LIVE",
  title: "Raf Simons Riot Bomber",
  subtitle: "Autumn Winter 2001-2002",
  description: "Archival riot bomber in museum condition.",
  specs: {
    category: "APPAREL",
    brand: "Raf Simons",
    season_era: "AW01 Riot! Riot! Riot!",
    tagged_size: "48",
    condition_grade: "ARCHIVAL_MINT",
    measurements_cm: {
      chest: 56,
      shoulders: 50,
      length: 68,
      sleeve: 64,
    },
    materials: ["Cotton", "Riri Zippers"],
  },
  start_price: "1000.00",
  reserve_price: "2500.00",
  buy_now_price: "4000.00",
  min_bid_increment: "50.00",
  current_price: "1000.00",
  min_valid_bid: "1000.00",
  bid_count: 0,
  is_buy_now_available: true,
  is_reserve_met: false,
  anti_snipe_extensions_count: 0,
  starts_at: "2026-10-31T12:00:00.000Z",
  ends_at: "2026-10-31T18:00:00.000Z",
  media: [],
  server_time: "2026-10-31T12:00:00.000Z",
};

const mockUserProfile: UserProfile = {
  id: "user-123",
  email: "collector@obsolete.vault",
  username: "archivist",
  role: "MEMBER",
  is_active: true,
  avatar_url: null,
  bio: "Archival researcher",
  available_balance: "5000.00",
  held_balance: "0.00",
  claimable_balance: "0.00",
};

describe("applyLotWsEvent pure reducer", () => {
  it("updates lot state accurately on LOT_SNAPSHOT", () => {
    const updated = applyLotWsEvent(mockBaseLot, {
      event_type: "LOT_SNAPSHOT",
      lot_id: mockBaseLot.id,
      status: "LIVE",
      current_price: "1500.00",
      min_valid_bid: "1550.00",
      bid_count: 5,
      leader_user_id: "leader-456",
      leader_username_masked: "l***6",
      is_buy_now_available: true,
      is_reserve_met: false,
      ends_at: "2026-10-31T18:00:00.000Z",
      anti_snipe_extensions_count: 0,
      server_time: "2026-10-31T14:00:00.000Z",
    });

    expect(updated).not.toBeNull();
    expect(updated?.current_price).toBe("1500.00");
    expect(updated?.min_valid_bid).toBe("1550.00");
    expect(updated?.bid_count).toBe(5);
    expect(updated?.leader_user_id).toBe("leader-456");
  });

  it("updates current_price, min_valid_bid, and reserve/buy-now status on BID_PLACED", () => {
    const updated = applyLotWsEvent(mockBaseLot, {
      event_type: "BID_PLACED",
      lot_id: mockBaseLot.id,
      bid_id: "bid-1",
      amount: "2600.00",
      min_valid_bid: "2650.00",
      bid_count: 6,
      leader_user_id: "leader-999",
      leader_username_masked: "l***9",
      is_buy_now_available: false,
      is_reserve_met: true,
      ends_at: "2026-10-31T18:02:00.000Z",
      triggered_anti_snipe: true,
      server_time: "2026-10-31T17:59:00.000Z",
    });

    expect(updated?.current_price).toBe("2600.00");
    expect(updated?.min_valid_bid).toBe("2650.00");
    expect(updated?.is_buy_now_available).toBe(false);
    expect(updated?.is_reserve_met).toBe(true);
    expect(updated?.anti_snipe_extensions_count).toBe(1);
    expect(updated?.ends_at).toBe("2026-10-31T18:02:00.000Z");
  });

  it("updates ends_at and anti_snipe_extensions_count on LOT_EXTENDED", () => {
    const updated = applyLotWsEvent(mockBaseLot, {
      event_type: "LOT_EXTENDED",
      lot_id: mockBaseLot.id,
      new_ends_at: "2026-10-31T18:04:00.000Z",
      anti_snipe_extensions_count: 2,
      server_time: "2026-10-31T18:01:50.000Z",
    });

    expect(updated?.ends_at).toBe("2026-10-31T18:04:00.000Z");
    expect(updated?.anti_snipe_extensions_count).toBe(2);
  });

  it("transitions to ENDED_WON with final price on LOT_SOLD", () => {
    const updated = applyLotWsEvent(mockBaseLot, {
      event_type: "LOT_SOLD",
      lot_id: mockBaseLot.id,
      winner_user_id: "winner-777",
      final_price: "4000.00",
      via_buy_now: true,
      server_time: "2026-10-31T14:30:00.000Z",
    });

    expect(updated?.status).toBe("ENDED_WON");
    expect(updated?.current_price).toBe("4000.00");
    expect(updated?.leader_user_id).toBe("winner-777");
    expect(updated?.is_buy_now_available).toBe(false);
  });

  it("transitions to final status on LOT_ENDED", () => {
    const updated = applyLotWsEvent(mockBaseLot, {
      event_type: "LOT_ENDED",
      lot_id: mockBaseLot.id,
      status: "ENDED_UNSOLD",
      winner_user_id: null,
      final_price: "1200.00",
      server_time: "2026-10-31T18:00:00.000Z",
    });

    expect(updated?.status).toBe("ENDED_UNSOLD");
    expect(updated?.leader_user_id).toBeNull();
    expect(updated?.is_buy_now_available).toBe(false);
  });

  it("returns null when current lot is null", () => {
    const updated = applyLotWsEvent(null, {
      event_type: "LOT_EXTENDED",
      lot_id: mockBaseLot.id,
      new_ends_at: "2026-10-31T18:04:00.000Z",
      anti_snipe_extensions_count: 1,
      server_time: "2026-10-31T18:01:50.000Z",
    });

    expect(updated).toBeNull();
  });
});

describe("useLiveLotSocket hook reactive updates", () => {
  const originalWebSocket = globalThis.WebSocket;

  beforeEach(() => {
    MockWebSocket.instances = [];
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    useAuthStore.getState().clearSession();
  });

  afterEach(() => {
    cleanup();
    globalThis.WebSocket = originalWebSocket;
    vi.restoreAllMocks();
  });

  it("connects to /lots/{lot_id} and reactively updates price, ends_at, and buy_now availability", async () => {
    const { result } = renderHook(() =>
      useLiveLotSocket(mockBaseLot.id, {
        initialLot: mockBaseLot,
      }),
    );

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const socket = MockWebSocket.instances[0];
    if (!socket) {
      throw new Error("Socket expected");
    }
    expect(socket.url).toContain(`/lots/${mockBaseLot.id}`);

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    act(() => {
      socket.emit({
        event_type: "BID_PLACED",
        lot_id: mockBaseLot.id,
        bid_id: "bid-xyz",
        amount: "1750.00",
        min_valid_bid: "1800.00",
        bid_count: 3,
        leader_user_id: "leader-1",
        leader_username_masked: "l***1",
        is_buy_now_available: true,
        is_reserve_met: false,
        ends_at: "2026-10-31T18:00:00.000Z",
        triggered_anti_snipe: false,
        server_time: "2026-10-31T15:00:00.000Z",
      });
    });

    expect(result.current.lot?.current_price).toBe("1750.00");
    expect(result.current.lot?.min_valid_bid).toBe("1800.00");
    expect(result.current.lot?.bid_count).toBe(3);
    expect(result.current.lot?.is_buy_now_available).toBe(true);
    expect(result.current.recentEvents.length).toBe(1);

    act(() => {
      socket.emit({
        event_type: "LOT_EXTENDED",
        lot_id: mockBaseLot.id,
        new_ends_at: "2026-10-31T18:02:00.000Z",
        anti_snipe_extensions_count: 1,
        server_time: "2026-10-31T17:59:10.000Z",
      });
    });

    expect(result.current.lot?.ends_at).toBe("2026-10-31T18:02:00.000Z");
    expect(result.current.lot?.anti_snipe_extensions_count).toBe(1);
    expect(result.current.isAntiSnipeExtended).toBe(true);

    act(() => {
      result.current.dismissAntiSnipeAlert();
    });
    expect(result.current.isAntiSnipeExtended).toBe(false);

    act(() => {
      socket.emit({
        event_type: "BID_PLACED",
        lot_id: mockBaseLot.id,
        bid_id: "bid-reserve-breaker",
        amount: "2600.00",
        min_valid_bid: "2650.00",
        bid_count: 4,
        leader_user_id: "leader-2",
        leader_username_masked: "l***2",
        is_buy_now_available: false,
        is_reserve_met: true,
        ends_at: "2026-10-31T18:02:00.000Z",
        triggered_anti_snipe: false,
        server_time: "2026-10-31T17:59:30.000Z",
      });
    });

    expect(result.current.lot?.current_price).toBe("2600.00");
    expect(result.current.lot?.is_buy_now_available).toBe(false);
    expect(result.current.lot?.is_reserve_met).toBe(true);
  });

  it("syncs clock offset with server_time on incoming websocket frames", async () => {
    const clientNowMs = Date.parse("2026-10-31T17:00:00.000Z");
    vi.spyOn(Date, "now").mockReturnValue(clientNowMs);

    renderHook(() =>
      useLiveLotSocket(mockBaseLot.id, {
        initialLot: mockBaseLot,
      }),
    );

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const socket = MockWebSocket.instances[0];
    if (!socket) {
      throw new Error("Socket expected");
    }
    const serverTimeIso = "2026-10-31T16:59:30.000Z";

    act(() => {
      socket.emit({
        event_type: "LOT_SNAPSHOT",
        lot_id: mockBaseLot.id,
        status: "LIVE",
        current_price: "1000.00",
        min_valid_bid: "1050.00",
        bid_count: 0,
        leader_user_id: null,
        leader_username_masked: null,
        is_buy_now_available: true,
        is_reserve_met: false,
        ends_at: "2026-10-31T18:00:00.000Z",
        anti_snipe_extensions_count: 0,
        server_time: serverTimeIso,
      });
    });

    expect(getClockOffsetMs()).toBe(-30_000);
  });

  it("closes socket on unmount", async () => {
    const { unmount } = renderHook(() =>
      useLiveLotSocket(mockBaseLot.id, {
        initialLot: mockBaseLot,
      }),
    );

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const socket = MockWebSocket.instances[0];
    if (!socket) {
      throw new Error("Socket expected");
    }

    let closed = false;
    socket.close = () => {
      closed = true;
    };

    unmount();
    expect(closed).toBe(true);
  });
});

describe("useUserNotificationsSocket and ClaimableHoldsBanner integration", () => {
  const originalWebSocket = globalThis.WebSocket;

  beforeEach(() => {
    MockWebSocket.instances = [];
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    useAuthStore.getState().clearSession();
  });

  afterEach(() => {
    cleanup();
    globalThis.WebSocket = originalWebSocket;
    vi.restoreAllMocks();
  });

  it("useUserNotificationsSocket connects to /user/notifications when authenticated and tracks connection", async () => {
    useAuthStore.getState().setSession("test-access-token", mockUserProfile);

    const { result, unmount } = renderHook(() => useUserNotificationsSocket());

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const socket = MockWebSocket.instances[0];
    if (!socket) {
      throw new Error("Socket expected");
    }
    expect(socket.url).toContain("/user/notifications");

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    unmount();
  });

  it("connects to /user/notifications and triggers ClaimableHoldsBanner upon HOLD_BECAME_CLAIMABLE", async () => {
    useAuthStore.getState().setSession("test-access-token", mockUserProfile);

    render(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(
          AppShell,
          null,
          React.createElement("div", { "data-testid": "test-content" }, "ARCHIVAL CONTENT"),
        ),
      ),
    );

    expect(screen.queryByTestId("claimable-holds-banner")).toBeNull();

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const notificationSocket = MockWebSocket.instances[0];
    if (!notificationSocket) {
      throw new Error("Notification socket expected");
    }
    expect(notificationSocket.url).toContain("/user/notifications");

    act(() => {
      notificationSocket.emit({
        event_type: "HOLD_BECAME_CLAIMABLE",
        hold_id: "hold-outbid-001",
        lot_id: mockBaseLot.id,
        lot_title: mockBaseLot.title,
        amount: "1500.00",
        reason: "OUTBID",
        new_claimable_balance: "1500.00",
        server_time: "2026-10-31T17:05:00.000Z",
      });
    });

    const banner = await screen.findByTestId("claimable-holds-banner");
    expect(banner).toBeDefined();
    expect(banner.textContent).toContain("YOU HAVE");
    expect(banner.textContent).toContain("$1500.00 USD");
    expect(banner.textContent).toContain("1 OUTBID HOLD");

    const claimPostSpy = vi.spyOn(apiClient, "post").mockResolvedValueOnce({
      claimed_count: 1,
      claimed_amount: "1500.00",
      claimed_hold_ids: ["hold-outbid-001"],
      available_balance: "6500.00",
      held_balance: "0.00",
      claimable_balance: "0.00",
      server_time: "2026-10-31T17:05:10.000Z",
    });

    const claimAllButton = screen.getByRole("button", {
      name: /CLAIM ALL \(\$1500\.00\)/i,
    });
    const user = userEvent.setup();
    await user.click(claimAllButton);

    expect(claimPostSpy).toHaveBeenCalledWith("/wallet/claims/claim-all");

    await waitFor(() => {
      expect(screen.queryByTestId("claimable-holds-banner")).toBeNull();
    });

    expect(useAuthStore.getState().user?.available_balance).toBe("6500.00");
    expect(useAuthStore.getState().user?.claimable_balance).toBe("0.00");
    expect(useAuthStore.getState().claimableCount).toBe(0);
  });

  it("normalizes websocket url whether or not path contains /ws prefix", () => {
    const url1 = buildWsUrl("/lots/123");
    const url2 = buildWsUrl("/ws/lots/123");
    expect(url1).toBe(url2);
    expect(url1).toContain("/ws/lots/123");
  });

  it("decrements held_balance and increments claimable_balance on HOLD_BECAME_CLAIMABLE", async () => {
    useAuthStore.getState().setSession("test-access-token", {
      ...mockUserProfile,
      held_balance: "1500.00",
      claimable_balance: "0.00",
    });

    const { unmount } = renderHook(() => useUserNotificationsSocket());

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const socket = MockWebSocket.instances[0];
    if (!socket) {
      throw new Error("Socket expected");
    }

    act(() => {
      socket.emit({
        event_type: "HOLD_BECAME_CLAIMABLE",
        hold_id: "hold-outbid-002",
        lot_id: mockBaseLot.id,
        lot_title: mockBaseLot.title,
        amount: "1500.00",
        reason: "OUTBID",
        new_claimable_balance: "1500.00",
        server_time: "2026-10-31T17:10:00.000Z",
      });
    });

    expect(useAuthStore.getState().user?.held_balance).toBe("0.00");
    expect(useAuthStore.getState().user?.claimable_balance).toBe("1500.00");

    act(() => {
      useAuthStore.getState().updateBalances({ available_balance: "9999.00" });
    });

    expect(MockWebSocket.instances.length).toBe(1);
    unmount();
  });

  it("refreshLot preserves newer websocket state if REST response arrives late", async () => {
    let resolveApiGet: (lot: LotDetail) => void = () => {};
    const apiPromise = new Promise<LotDetail>((resolve) => {
      resolveApiGet = resolve;
    });
    vi.spyOn(apiClient, "get").mockReturnValueOnce(apiPromise);

    const { result } = renderHook(() =>
      useLiveLotSocket(mockBaseLot.id),
    );

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const socket = MockWebSocket.instances[0];
    if (!socket) {
      throw new Error("Socket expected");
    }

    act(() => {
      socket.emit({
        event_type: "BID_PLACED",
        lot_id: mockBaseLot.id,
        bid_id: "bid-fast",
        amount: "3000.00",
        min_valid_bid: "3050.00",
        bid_count: 5,
        leader_user_id: "leader-5",
        leader_username_masked: "l***5",
        is_buy_now_available: false,
        is_reserve_met: true,
        ends_at: "2026-10-31T18:02:00.000Z",
        triggered_anti_snipe: true,
        server_time: "2026-10-31T17:59:30.000Z",
      });
    });

    expect(result.current.lot).toBeNull();

    act(() => {
      resolveApiGet({
        ...mockBaseLot,
        current_price: "1000.00",
        bid_count: 0,
        server_time: "2026-10-31T17:59:10.000Z",
      });
    });

    await waitFor(() => {
      expect(result.current.lot?.current_price).toBe("3000.00");
    });
    expect(result.current.lot?.bid_count).toBe(5);
  });

  it("hydrates historical bids from GET /lots/{id} and prevents duplicate entries on websocket BID_PLACED", async () => {
    const historicalBids = [
      {
        id: "bid-hist-1",
        bidder_id: "user-alpha",
        bidder_username_masked: "a***a",
        amount: "1100.00",
        is_buy_now: false,
        triggered_anti_snipe: false,
        created_at: "2026-10-31T12:10:00.000Z",
      },
      {
        id: "bid-hist-2",
        bidder_id: "user-beta",
        bidder_username_masked: "b***a",
        amount: "1200.00",
        is_buy_now: false,
        triggered_anti_snipe: false,
        created_at: "2026-10-31T12:20:00.000Z",
      },
    ];

    vi.spyOn(apiClient, "get").mockResolvedValueOnce({
      ...mockBaseLot,
      current_price: "1200.00",
      bid_count: 2,
      bids: historicalBids,
    });

    const { result } = renderHook(() =>
      useLiveLotSocket(mockBaseLot.id),
    );

    await waitFor(() => {
      expect(result.current.recentEvents.length).toBe(2);
    });

    expect(result.current.recentEvents[0]?.event_type).toBe("BID_PLACED");
    if (result.current.recentEvents[0]?.event_type === "BID_PLACED") {
      expect(result.current.recentEvents[0].bid_id).toBe("bid-hist-2");
      expect(result.current.recentEvents[0].amount).toBe("1200.00");
    }

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const socket = MockWebSocket.instances[0];
    if (!socket) {
      throw new Error("Socket expected");
    }

    act(() => {
      socket.emit({
        event_type: "BID_PLACED",
        lot_id: mockBaseLot.id,
        bid_id: "bid-hist-2",
        amount: "1200.00",
        min_valid_bid: "1250.00",
        bid_count: 2,
        leader_user_id: "user-beta",
        leader_username_masked: "b***a",
        is_buy_now_available: true,
        is_reserve_met: false,
        ends_at: "2026-10-31T18:00:00.000Z",
        triggered_anti_snipe: false,
        server_time: "2026-10-31T12:20:00.000Z",
      });
    });

    expect(result.current.recentEvents.length).toBe(2);

    act(() => {
      socket.emit({
        event_type: "BID_PLACED",
        lot_id: mockBaseLot.id,
        bid_id: "bid-live-3",
        amount: "1300.00",
        min_valid_bid: "1350.00",
        bid_count: 3,
        leader_user_id: "user-gamma",
        leader_username_masked: "g***a",
        is_buy_now_available: true,
        is_reserve_met: false,
        ends_at: "2026-10-31T18:00:00.000Z",
        triggered_anti_snipe: false,
        server_time: "2026-10-31T12:30:00.000Z",
      });
    });

    expect(result.current.recentEvents.length).toBe(3);
    expect(result.current.recentEvents[0]?.event_type).toBe("BID_PLACED");
    if (result.current.recentEvents[0]?.event_type === "BID_PLACED") {
      expect(result.current.recentEvents[0].bid_id).toBe("bid-live-3");
      expect(result.current.recentEvents[0].amount).toBe("1300.00");
    }
  });

  it("hydrates historical bids immediately when initialLot contains bids", () => {
    const lotWithBids = {
      ...mockBaseLot,
      current_price: "1500.00",
      bid_count: 1,
      bids: [
        {
          id: "bid-initial-1",
          bidder_id: "user-init",
          bidder_username_masked: "i***t",
          amount: "1500.00",
          is_buy_now: false,
          triggered_anti_snipe: false,
          created_at: "2026-10-31T14:00:00.000Z",
        },
      ],
    };

    const { result } = renderHook(() =>
      useLiveLotSocket(mockBaseLot.id, { initialLot: lotWithBids }),
    );

    expect(result.current.recentEvents.length).toBe(1);
    expect(result.current.recentEvents[0]?.event_type).toBe("BID_PLACED");
    if (result.current.recentEvents[0]?.event_type === "BID_PLACED") {
      expect(result.current.recentEvents[0].bid_id).toBe("bid-initial-1");
      expect(result.current.recentEvents[0].amount).toBe("1500.00");
    }
  });

  it("fetches lot details via apiClient.get when initialLot is null", async () => {
    const getSpy = vi
      .spyOn(apiClient, "get")
      .mockResolvedValueOnce(mockBaseLot);

    const { result } = renderHook(() =>
      useLiveLotSocket(mockBaseLot.id, { initialLot: null }),
    );

    await waitFor(() => {
      expect(result.current.lot).not.toBeNull();
    });

    expect(getSpy).toHaveBeenCalledTimes(1);
    expect(result.current.lot?.id).toBe(mockBaseLot.id);
    expect(result.current.isLoading).toBe(false);
  });
});

