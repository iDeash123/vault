import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../../src/App";
import { useAuthStore } from "../../src/shared/store/authStore";
import { resetClockOffset } from "../../src/shared/store/clockStore";
import type { UserProfile } from "../../src/shared/types/domain";

const MOCK_SELLER: UserProfile = {
  id: "seller-uuid-1111-1111-111111111111",
  email: "seller@obsolete.io",
  username: "archival_vault",
  role: "MEMBER",
  is_active: true,
  avatar_url: null,
  bio: "Seller of rare archival garments",
  available_balance: "500.00",
  held_balance: "0.00",
  claimable_balance: "0.00",
};

const MOCK_BUYER: UserProfile = {
  id: "buyer-uuid-2222-2222-222222222222",
  email: "buyer@obsolete.io",
  username: "synth_collector",
  role: "MEMBER",
  is_active: true,
  avatar_url: null,
  bio: "Buyer and sound collector",
  available_balance: "1000.00",
  held_balance: "3500.00",
  claimable_balance: "0.00",
};

const INITIAL_ORDER_FUNDS_HELD = {
  id: "order-held-001",
  lot_id: "lot-001",
  lot_title: "Raf Simons AW01 Riot Camo Bomber",
  buyer_id: "buyer-uuid-2222-2222-222222222222",
  seller_id: "seller-uuid-1111-1111-111111111111",
  wallet_hold_id: "hold-001",
  final_amount: "1200.00",
  platform_fee_amount: "96.00",
  seller_payout_amount: "1104.00",
  status: "FUNDS_HELD",
  tracking_number: null,
  shipping_carrier: null,
  shipped_at: null,
  completed_at: null,
  dispute_reason: null,
  created_at: "2026-10-27T12:00:00Z",
  updated_at: "2026-10-27T12:00:00Z",
  server_time: "2026-10-27T12:00:00Z",
};

const INITIAL_ORDER_SHIPPED = {
  id: "order-shipped-002",
  lot_id: "lot-002",
  lot_title: "Roland TR-808 Rhythm Composer",
  buyer_id: "buyer-uuid-2222-2222-222222222222",
  seller_id: "seller-uuid-1111-1111-111111111111",
  wallet_hold_id: "hold-002",
  final_amount: "3500.00",
  platform_fee_amount: "280.00",
  seller_payout_amount: "3220.00",
  status: "SHIPPED",
  tracking_number: "DHL-987654321",
  shipping_carrier: "DHL Express",
  shipped_at: "2026-10-27T13:00:00Z",
  completed_at: null,
  dispute_reason: null,
  created_at: "2026-10-27T11:00:00Z",
  updated_at: "2026-10-27T13:00:00Z",
  server_time: "2026-10-27T13:00:00Z",
};

describe("OrdersPage escrow dashboard flows", () => {
  beforeEach(() => {
    cleanup();
    vi.restoreAllMocks();
    useAuthStore.getState().clearSession();
    resetClockOffset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    useAuthStore.getState().clearSession();
    resetClockOffset();
  });

  it("renders seller view and submits tracking number via shipping dispatch form", async () => {
    useAuthStore.getState().setSession("jwt-seller-token", MOCK_SELLER);

    let shipCallPayload: { shipping_carrier: string; tracking_number: string } | null = null;

    const fetchMock = vi.fn().mockImplementation((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/orders")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [INITIAL_ORDER_FUNDS_HELD],
              total: 1,
              server_time: "2026-10-27T12:00:00Z",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      if (url.endsWith(`/api/v1/orders/${INITIAL_ORDER_FUNDS_HELD.id}/ship`)) {
        if (init?.body && typeof init.body === "string") {
          shipCallPayload = JSON.parse(init.body) as {
            shipping_carrier: string;
            tracking_number: string;
          };
        }
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...INITIAL_ORDER_FUNDS_HELD,
              status: "SHIPPED",
              shipping_carrier: "DHL Express",
              tracking_number: "DHL-987654321",
              shipped_at: "2026-10-27T14:30:00Z",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected fetch URL: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/orders"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Raf Simons AW01 Riot Camo Bomber")).toBeDefined();
    });

    expect(screen.getByText("ESCROW LOCKED")).toBeDefined();
    expect(screen.getByText("SELLER")).toBeDefined();
    expect(screen.getByText("$1200.00")).toBeDefined();
    expect(screen.getByText("Net Payout: $1104.00")).toBeDefined();

    const dispatchBtn = screen.getByRole("button", { name: /dispatch shipment/i });
    fireEvent.click(dispatchBtn);

    await waitFor(() => {
      expect(screen.getByLabelText(/shipping carrier/i)).toBeDefined();
    });

    fireEvent.change(screen.getByLabelText(/shipping carrier/i), {
      target: { value: "DHL Express" },
    });
    fireEvent.change(screen.getByLabelText(/tracking number/i), {
      target: { value: "DHL-987654321" },
    });

    const submitBtn = screen.getByRole("button", { name: /confirm dispatch/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText("IN TRANSIT")).toBeDefined();
    });

    expect(shipCallPayload).toEqual({
      shipping_carrier: "DHL Express",
      tracking_number: "DHL-987654321",
    });

    expect(screen.getByText("DHL-987654321")).toBeDefined();
  });

  it("renders buyer view and confirms receipt via Confirm Receipt & Release Escrow button", async () => {
    useAuthStore.getState().setSession("jwt-buyer-token", MOCK_BUYER);

    let confirmReceiptCalled = false;

    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/orders")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [INITIAL_ORDER_SHIPPED],
              total: 1,
              server_time: "2026-10-27T13:00:00Z",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      if (url.endsWith(`/api/v1/orders/${INITIAL_ORDER_SHIPPED.id}/confirm-receipt`)) {
        confirmReceiptCalled = true;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...INITIAL_ORDER_SHIPPED,
              status: "COMPLETED",
              completed_at: "2026-10-27T15:00:00Z",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected fetch URL: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/orders"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Roland TR-808 Rhythm Composer")).toBeDefined();
    });

    expect(screen.getByText("BUYER")).toBeDefined();
    expect(screen.getByText("IN TRANSIT")).toBeDefined();
    expect(screen.getByText("DHL-987654321")).toBeDefined();

    const confirmBtn = screen.getByRole("button", {
      name: /confirm receipt & release escrow/i,
    });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByText("COMPLETED & RELEASED")).toBeDefined();
    });

    expect(confirmReceiptCalled).toBe(true);
    expect(
      screen.getByText(/Receipt confirmed. Escrow funds released to seller./i),
    ).toBeDefined();
    expect(useAuthStore.getState().user?.held_balance).toBe("0.00");
  });

  it("supports opening a dispute and submitting dispute reason", async () => {
    useAuthStore.getState().setSession("jwt-buyer-token", MOCK_BUYER);

    let disputePayload: { dispute_reason: string } | null = null;

    const fetchMock = vi.fn().mockImplementation((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/orders")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [INITIAL_ORDER_SHIPPED],
              total: 1,
              server_time: "2026-10-27T13:00:00Z",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      if (url.endsWith(`/api/v1/orders/${INITIAL_ORDER_SHIPPED.id}/dispute`)) {
        if (init?.body && typeof init.body === "string") {
          disputePayload = JSON.parse(init.body) as { dispute_reason: string };
        }
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...INITIAL_ORDER_SHIPPED,
              status: "DISPUTED",
              dispute_reason: "Item arrived damaged with broken knobs",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected fetch URL: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/orders"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Roland TR-808 Rhythm Composer")).toBeDefined();
    });

    const disputeBtn = screen.getByRole("button", { name: /open dispute/i });
    fireEvent.click(disputeBtn);

    await waitFor(() => {
      expect(screen.getByLabelText(/dispute reason/i)).toBeDefined();
    });

    fireEvent.change(screen.getByLabelText(/dispute reason/i), {
      target: { value: "Item arrived damaged with broken knobs" },
    });

    const submitDisputeBtn = screen.getByRole("button", { name: /submit dispute/i });
    fireEvent.click(submitDisputeBtn);

    await waitFor(() => {
      expect(screen.getByText("UNDER ARBITRATION")).toBeDefined();
    });

    expect(disputePayload).toEqual({
      dispute_reason: "Item arrived damaged with broken knobs",
    });
    expect(
      screen.getByText(/Item arrived damaged with broken knobs/i),
    ).toBeDefined();
  });

  it("filters orders by role and status tabs", async () => {
    useAuthStore.getState().setSession("jwt-buyer-token", MOCK_BUYER);

    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/orders")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [INITIAL_ORDER_FUNDS_HELD, INITIAL_ORDER_SHIPPED],
              total: 2,
              server_time: "2026-10-27T13:00:00Z",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected fetch URL: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/orders"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Raf Simons AW01 Riot Camo Bomber")).toBeDefined();
      expect(screen.getByText("Roland TR-808 Rhythm Composer")).toBeDefined();
    });

    const fundsHeldFilter = screen.getByRole("button", { name: /funds held/i });
    fireEvent.click(fundsHeldFilter);

    expect(screen.getByText("Raf Simons AW01 Riot Camo Bomber")).toBeDefined();
    expect(screen.queryByText("Roland TR-808 Rhythm Composer")).toBeNull();
  });

  it("renders authentication required notice when user is not logged in", () => {
    render(
      <MemoryRouter initialEntries={["/orders"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(screen.getByText("AUTHENTICATION REQUIRED")).toBeDefined();
    expect(screen.getByRole("button", { name: "LOG IN" })).toBeDefined();
  });
});
