import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../../src/shared/api/client";
import { useAuthStore } from "../../src/shared/store/authStore";
import type { LotDetail, UserProfile } from "../../src/shared/types/domain";
import { AntiSnipeAlert } from "../../src/domains/live-auction/AntiSnipeAlert";
import { BidActionPanel } from "../../src/domains/live-auction/BidActionPanel";
import { LiveBidFeed } from "../../src/domains/live-auction/LiveBidFeed";
import { LiveLotPage } from "../../src/domains/live-auction/LiveLotPage";

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

const mockTestLot: LotDetail = {
  id: "00000000-0000-0000-0000-000000000001",
  seller_id: "00000000-0000-0000-0000-000000000002",
  leader_user_id: null,
  category: "APPAREL",
  status: "LIVE",
  title: "Raf Simons Riot Bomber",
  subtitle: "AW01 Riot! Riot! Riot!",
  description: "Museum piece bomber jacket with original zippers.",
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
    materials: ["100% Cotton", "Riri Zippers"],
  },
  start_price: "1000.00",
  reserve_price: "2500.00",
  buy_now_price: "4500.00",
  min_bid_increment: "50.00",
  current_price: "1000.00",
  min_valid_bid: "1000.00",
  bid_count: 0,
  is_buy_now_available: true,
  is_reserve_met: false,
  anti_snipe_extensions_count: 0,
  starts_at: "2026-10-31T12:00:00.000Z",
  ends_at: "2026-10-31T18:00:00.000Z",
  media: [
    {
      id: "media-1",
      slot_type: "PRIMARY",
      public_url: "https://cdn.obsolete.vault/lots/raf-front.jpg",
      mime_type: "image/jpeg",
      sort_order: 0,
    },
    {
      id: "media-2",
      slot_type: "TAG_STAMP",
      public_url: "https://cdn.obsolete.vault/lots/raf-tag.jpg",
      mime_type: "image/jpeg",
      sort_order: 1,
    },
    {
      id: "media-3",
      slot_type: "DEFECT",
      public_url: "https://cdn.obsolete.vault/lots/raf-defect.jpg",
      mime_type: "image/jpeg",
      sort_order: 2,
    },
    {
      id: "media-4",
      slot_type: "DETAIL",
      public_url: "https://cdn.obsolete.vault/lots/raf-detail.jpg",
      mime_type: "image/jpeg",
      sort_order: 3,
    },
  ],
  server_time: "2026-10-31T12:00:00.000Z",
};

const mockCollector: UserProfile = {
  id: "user-buyer-100",
  email: "buyer@obsolete.vault",
  username: "archivist",
  role: "MEMBER",
  is_active: true,
  avatar_url: null,
  bio: "Collector",
  available_balance: "10000.00",
  held_balance: "0.00",
  claimable_balance: "0.00",
};

describe("AntiSnipeAlert component", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders nothing when isExtended is false", () => {
    const { container } = render(
      <AntiSnipeAlert isExtended={false} extensionsCount={0} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("displays ANTI-SNIPE EXTENDED (+2:00) banner when isExtended is true", () => {
    const dismissSpy = vi.fn();
    render(
      <AntiSnipeAlert
        isExtended={true}
        extensionsCount={1}
        onDismiss={dismissSpy}
      />,
    );

    const alert = screen.getByTestId("anti-snipe-alert");
    expect(alert).toBeDefined();
    expect(alert.textContent).toContain("ANTI-SNIPE EXTENDED (+2:00)");
    expect(alert.textContent).toContain("EXTENSION #1");

    const dismissButton = screen.getByRole("button", { name: /DISMISS/i });
    fireEvent.click(dismissButton);
    expect(dismissSpy).toHaveBeenCalledTimes(1);
  });
});

describe("BidActionPanel component", () => {
  beforeEach(() => {
    useAuthStore.getState().clearSession();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("enforces minimum bid step >= min_valid_bid and submits bid with Idempotency-Key", async () => {
    useAuthStore.getState().setSession("auth-token-1", mockCollector);

    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValueOnce({
      id: "bid-created-1",
      lot_id: mockTestLot.id,
      bidder_id: mockCollector.id,
      amount: "1050.00",
      server_time: "2026-10-31T12:01:00.000Z",
    });

    render(
      <MemoryRouter>
        <BidActionPanel lot={mockTestLot} />
      </MemoryRouter>,
    );

    const bidInput = screen.getByLabelText(/BID AMOUNT \(USD\)/i);
    expect(bidInput).toBeDefined();

    const placeBidButton = screen.getByRole("button", { name: /PLACE BID/i });
    expect(placeBidButton).toBeDefined();

    const user = userEvent.setup();
    await user.clear(bidInput);
    await user.type(bidInput, "500.00");

    expect(placeBidButton.hasAttribute("disabled")).toBe(true);

    await user.clear(bidInput);
    await user.type(bidInput, "1050.00");
    expect(placeBidButton.hasAttribute("disabled")).toBe(false);

    await user.click(placeBidButton);

    expect(postSpy).toHaveBeenCalledTimes(1);
    const callArgs = postSpy.mock.calls[0];
    if (!callArgs) {
      throw new Error("Expected call args");
    }
    expect(callArgs[0]).toBe(`/lots/${mockTestLot.id}/bids`);
    expect(callArgs[1]).toEqual({ amount: "1050.00" });

    const requestHeaders = callArgs[2];
    expect(requestHeaders?.["Idempotency-Key"]).toBeDefined();
    expect(requestHeaders?.["Idempotency-Key"]?.length).toBeGreaterThan(0);

    await screen.findByTestId("bid-panel-success");
    expect(useAuthStore.getState().user?.available_balance).toBe("8950.00");
    expect(useAuthStore.getState().user?.held_balance).toBe("1050.00");
  });

  it("reads latest user balances from store after bid request to prevent clobbering outbid updates", async () => {
    useAuthStore.getState().setSession("auth-token-1", {
      ...mockCollector,
      available_balance: "10000.00",
      held_balance: "2000.00",
      claimable_balance: "0.00",
    });

    vi.spyOn(apiClient, "post").mockImplementation(() => {
      useAuthStore.getState().updateBalances({
        held_balance: "500.00",
        claimable_balance: "1500.00",
      });
      return Promise.resolve({
        bid_id: "bid-outbid-race-1",
        lot_id: mockTestLot.id,
        amount: "1050.00",
        created_at: "2026-10-31T12:01:00.000Z",
      });
    });

    render(
      <MemoryRouter>
        <BidActionPanel lot={mockTestLot} />
      </MemoryRouter>,
    );

    const bidInput = screen.getByLabelText<HTMLInputElement>(/BID AMOUNT \(USD\)/i);
    const placeBidButton = screen.getByRole("button", { name: /PLACE BID/i });

    const user = userEvent.setup();
    await user.clear(bidInput);
    await user.type(bidInput, "1050.00");
    await user.click(placeBidButton);

    await screen.findByTestId("bid-panel-success");
    expect(useAuthStore.getState().user?.held_balance).toBe("1550.00");
    expect(useAuthStore.getState().user?.claimable_balance).toBe("1500.00");
    expect(useAuthStore.getState().user?.available_balance).toBe("8950.00");
  });

  it("hides Buy Now button when is_buy_now_available is false", () => {
    useAuthStore.getState().setSession("auth-token-1", mockCollector);

    const lotWithoutBuyNow: LotDetail = {
      ...mockTestLot,
      is_buy_now_available: false,
    };

    render(
      <MemoryRouter>
        <BidActionPanel lot={lotWithoutBuyNow} />
      </MemoryRouter>,
    );

    expect(screen.queryByTestId("buy-now-button")).toBeNull();
  });

  it("shows Buy Now button when is_buy_now_available is true and executes buy-now with Idempotency-Key", async () => {
    useAuthStore.getState().setSession("auth-token-1", mockCollector);

    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValueOnce({
      order_id: "order-blitz-1",
      lot_id: mockTestLot.id,
      buyer_id: mockCollector.id,
      amount: "4500.00",
      order_status: "FUNDS_HELD",
      server_time: "2026-10-31T12:02:00.000Z",
    });

    render(
      <MemoryRouter>
        <BidActionPanel lot={mockTestLot} />
      </MemoryRouter>,
    );

    const buyNowContainer = screen.getByTestId("buy-now-button");
    expect(buyNowContainer).toBeDefined();

    const buyNowButton = screen.getByRole("button", { name: /BUY NOW/i });
    expect(buyNowButton.textContent).toContain("BUY NOW ($4500.00)");

    const user = userEvent.setup();
    await user.click(buyNowButton);

    expect(postSpy).toHaveBeenCalledTimes(1);
    const callArgs = postSpy.mock.calls[0];
    if (!callArgs) {
      throw new Error("Expected call args");
    }
    expect(callArgs[0]).toBe(`/lots/${mockTestLot.id}/buy-now`);

    const requestHeaders = callArgs[2];
    expect(requestHeaders?.["Idempotency-Key"]).toBeDefined();
    expect(requestHeaders?.["Idempotency-Key"]?.length).toBeGreaterThan(0);

    await screen.findByTestId("bid-panel-success");
    expect(useAuthStore.getState().user?.available_balance).toBe("5500.00");
    expect(useAuthStore.getState().user?.held_balance).toBe("4500.00");
  });

  it("reads latest user balances from store after buy-now request to prevent clobbering outbid updates", async () => {
    useAuthStore.getState().setSession("auth-token-1", {
      ...mockCollector,
      available_balance: "10000.00",
      held_balance: "1000.00",
      claimable_balance: "0.00",
    });

    vi.spyOn(apiClient, "post").mockImplementation(() => {
      useAuthStore.getState().updateBalances({
        held_balance: "200.00",
        claimable_balance: "800.00",
      });
      return Promise.resolve({
        order_id: "order-blitz-race",
        lot_id: mockTestLot.id,
        buyer_id: mockCollector.id,
        amount: "4500.00",
        order_status: "FUNDS_HELD",
        server_time: "2026-10-31T12:02:00.000Z",
      });
    });

    render(
      <MemoryRouter>
        <BidActionPanel lot={mockTestLot} />
      </MemoryRouter>,
    );

    const buyNowButton = screen.getByRole("button", { name: /BUY NOW/i });
    const user = userEvent.setup();
    await user.click(buyNowButton);

    await screen.findByTestId("bid-panel-success");
    expect(useAuthStore.getState().user?.held_balance).toBe("4700.00");
    expect(useAuthStore.getState().user?.claimable_balance).toBe("800.00");
    expect(useAuthStore.getState().user?.available_balance).toBe("5500.00");
  });

  it("preserves user-entered higher bid amount when min_valid_bid increments", () => {
    useAuthStore.getState().setSession("auth-token-1", mockCollector);

    const { rerender } = render(
      <MemoryRouter>
        <BidActionPanel lot={mockTestLot} />
      </MemoryRouter>,
    );

    const bidInput = screen.getByLabelText<HTMLInputElement>(/BID AMOUNT \(USD\)/i);
    fireEvent.change(bidInput, { target: { value: "3000.00" } });
    expect(bidInput.value).toBe("3000.00");

    rerender(
      <MemoryRouter>
        <BidActionPanel lot={{ ...mockTestLot, min_valid_bid: "1100.00" }} />
      </MemoryRouter>,
    );

    expect(bidInput.value).toBe("3000.00");

    rerender(
      <MemoryRouter>
        <BidActionPanel lot={{ ...mockTestLot, min_valid_bid: "3500.00" }} />
      </MemoryRouter>,
    );

    expect(bidInput.value).toBe("3500.00");
  });

  it("calculates quick increment step from valid base when current bid is below min_valid_bid", () => {
    useAuthStore.getState().setSession("auth-token-1", mockCollector);

    render(
      <MemoryRouter>
        <BidActionPanel lot={mockTestLot} />
      </MemoryRouter>,
    );

    const bidInput = screen.getByLabelText<HTMLInputElement>(/BID AMOUNT \(USD\)/i);
    fireEvent.change(bidInput, { target: { value: "100.00" } });

    const plusFiftyButton = screen.getByRole("button", { name: /\+\$50/i });
    fireEvent.click(plusFiftyButton);

    expect(bidInput.value).toBe("1050.00");
  });
});

describe("LiveBidFeed component", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders empty state when there are no events", () => {
    render(<LiveBidFeed events={[]} />);
    expect(screen.getByText(/NO LIVE BIDDING ACTIVITY YET/i)).toBeDefined();
  });

  it("renders bids and extensions correctly", () => {
    render(
      <LiveBidFeed
        events={[
          {
            event_type: "BID_PLACED",
            lot_id: mockTestLot.id,
            bid_id: "bid-1",
            amount: "1500.00",
            min_valid_bid: "1550.00",
            bid_count: 1,
            leader_user_id: "user-1",
            leader_username_masked: "a***1",
            is_buy_now_available: true,
            is_reserve_met: false,
            ends_at: "2026-10-31T18:00:00.000Z",
            triggered_anti_snipe: true,
            server_time: "2026-10-31T17:59:00.000Z",
          },
          {
            event_type: "LOT_EXTENDED",
            lot_id: mockTestLot.id,
            new_ends_at: "2026-10-31T18:02:00.000Z",
            anti_snipe_extensions_count: 1,
            server_time: "2026-10-31T17:59:00.000Z",
          },
        ]}
      />,
    );

    expect(screen.getByTestId("bid-feed-item-bid")).toBeDefined();
    expect(screen.getByText(/\$1500\.00/i)).toBeDefined();
    expect(screen.getByText(/BY a\*\*\*1/i)).toBeDefined();
    expect(screen.getByTestId("bid-feed-item-extended")).toBeDefined();
  });

  it("displays HIGH BIDDER tag when bid matches currentLeaderId", () => {
    render(
      <LiveBidFeed
        events={[
          {
            event_type: "BID_PLACED",
            lot_id: mockTestLot.id,
            bid_id: "bid-leader-1",
            amount: "1500.00",
            min_valid_bid: "1550.00",
            bid_count: 1,
            leader_user_id: "user-leader-xyz",
            leader_username_masked: "l***z",
            is_buy_now_available: true,
            is_reserve_met: false,
            ends_at: "2026-10-31T18:00:00.000Z",
            triggered_anti_snipe: false,
            server_time: "2026-10-31T17:50:00.000Z",
          },
        ]}
        currentLeaderId="user-leader-xyz"
      />,
    );

    const leaderTag = screen.getByTestId("bid-feed-leader-tag");
    expect(leaderTag).toBeDefined();
    expect(leaderTag.textContent).toContain("HIGH BIDDER");
  });
});

describe("LiveLotPage integration with WebSocket", () => {
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

  it("loads lot details, connects to websocket, and triggers ANTI-SNIPE EXTENDED (+2:00) on LOT_EXTENDED", async () => {
    useAuthStore.getState().setSession("test-token", mockCollector);

    vi.spyOn(apiClient, "get").mockResolvedValueOnce(mockTestLot);

    render(
      <MemoryRouter initialEntries={[`/lots/${mockTestLot.id}`]}>
        <Routes>
          <Route path="/lots/:lotId" element={<LiveLotPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByTestId("live-lot-page");

    expect(screen.getByText("Raf Simons Riot Bomber")).toBeDefined();
    expect(screen.getAllByText("AW01 Riot! Riot! Riot!").length).toBeGreaterThan(0);
    expect(screen.getByTestId("category-specs-table")).toBeDefined();
    expect(screen.getByTestId("countdown-timer")).toBeDefined();
    expect(screen.getAllByTestId("price-ticker").length).toBeGreaterThan(0);
    expect(screen.getByTestId("bid-action-panel")).toBeDefined();
    expect(screen.getByTestId("live-bid-feed")).toBeDefined();

    expect(screen.queryByTestId("anti-snipe-alert")).toBeNull();

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const lotSocket = MockWebSocket.instances[0];
    if (!lotSocket) {
      throw new Error("Lot socket expected");
    }

    act(() => {
      lotSocket.emit({
        event_type: "LOT_EXTENDED",
        lot_id: mockTestLot.id,
        new_ends_at: "2026-10-31T18:02:00.000Z",
        anti_snipe_extensions_count: 1,
        server_time: "2026-10-31T17:59:15.000Z",
      });
    });

    const alert = await screen.findByTestId("anti-snipe-alert");
    expect(alert).toBeDefined();
    expect(alert.textContent).toContain("ANTI-SNIPE EXTENDED (+2:00)");
  });

  it("hides buy now price ticker when buy now is not available", async () => {
    useAuthStore.getState().setSession("test-token", mockCollector);
    vi.spyOn(apiClient, "get").mockResolvedValueOnce({
      ...mockTestLot,
      is_buy_now_available: false,
    });

    render(
      <MemoryRouter initialEntries={[`/lots/${mockTestLot.id}`]}>
        <Routes>
          <Route path="/lots/:lotId" element={<LiveLotPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByTestId("live-lot-page");
    expect(screen.queryByText(/BUY NOW PRICE/i)).toBeNull();
  });

  it("does not enter infinite fetch loop when lot ends_at is already in the past", async () => {
    useAuthStore.getState().setSession("test-token", mockCollector);

    const pastLot: LotDetail = {
      ...mockTestLot,
      status: "LIVE",
      ends_at: "2020-01-01T00:00:00.000Z",
      server_time: "2026-10-31T12:00:00.000Z",
    };

    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue(pastLot);

    render(
      <MemoryRouter initialEntries={[`/lots/${mockTestLot.id}`]}>
        <Routes>
          <Route path="/lots/:lotId" element={<LiveLotPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByTestId("live-lot-page");

    await new Promise((resolve) => setTimeout(resolve, 350));

    expect(getSpy).toHaveBeenCalledTimes(1);
  });

  it("updates price ticker and bid feed upon receiving BID_PLACED websocket event", async () => {
    useAuthStore.getState().setSession("test-token", mockCollector);

    vi.spyOn(apiClient, "get").mockResolvedValueOnce(mockTestLot);

    render(
      <MemoryRouter initialEntries={[`/lots/${mockTestLot.id}`]}>
        <Routes>
          <Route path="/lots/:lotId" element={<LiveLotPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByTestId("live-lot-page");

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const lotSocket = MockWebSocket.instances[0];
    if (!lotSocket) {
      throw new Error("Lot socket expected");
    }

    act(() => {
      lotSocket.emit({
        event_type: "BID_PLACED",
        lot_id: mockTestLot.id,
        bid_id: "bid-live-update-1",
        amount: "1850.00",
        min_valid_bid: "1900.00",
        bid_count: 1,
        leader_user_id: "user-leader-999",
        leader_username_masked: "l***9",
        is_buy_now_available: true,
        is_reserve_met: false,
        ends_at: "2026-10-31T18:00:00.000Z",
        triggered_anti_snipe: false,
        server_time: "2026-10-31T14:00:00.000Z",
      });
    });

    await waitFor(() => {
      expect(screen.getByText("$1,850.00")).toBeDefined();
    });
    expect(screen.getByText("BIDS LOGGED: 1")).toBeDefined();
    expect(screen.getByTestId("bid-feed-item-bid")).toBeDefined();
    expect(screen.getByText("BY l***9")).toBeDefined();
  });
});

