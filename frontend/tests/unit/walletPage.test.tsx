import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../../src/App";
import { useAuthStore } from "../../src/shared/store/authStore";
import { resetClockOffset } from "../../src/shared/store/clockStore";
import type {
  UserProfile,
  WalletSummaryResponse,
} from "../../src/shared/types/domain";

const MOCK_USER: UserProfile = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "collector@obsolete.io",
  username: "raf_collector",
  role: "MEMBER",
  is_active: true,
  avatar_url: null,
  bio: "Archival collector",
  available_balance: "120.00",
  held_balance: "450.00",
  claimable_balance: "300.00",
};

const INITIAL_WALLET_SUMMARY: WalletSummaryResponse = {
  available_balance: "120.00",
  held_balance: "450.00",
  claimable_balance: "300.00",
  holds: [
    {
      id: "hold-claimable-001",
      lot_id: "lot-001",
      lot_title: "Raf Simons AW01 Riot! Riot! Riot! Camo Bomber",
      amount: "300.00",
      status: "CLAIMABLE",
      created_at: "2026-10-26T10:00:00Z",
      outbid_at: "2026-10-26T10:05:00Z",
      claimed_at: null,
    },
    {
      id: "hold-active-002",
      lot_id: "lot-002",
      lot_title: "Roland TR-808 Rhythm Composer",
      amount: "450.00",
      status: "ACTIVE_HOLD",
      created_at: "2026-10-26T10:10:00Z",
      outbid_at: null,
      claimed_at: null,
    },
  ],
  ledger_entries: [
    {
      id: "ledger-001",
      entry_type: "BID_OUTBID_TO_CLAIMABLE",
      amount: "300.00",
      available_delta: "0.00",
      held_delta: "-300.00",
      claimable_delta: "300.00",
      balance_available_after: "120.00",
      balance_held_after: "450.00",
      balance_claimable_after: "300.00",
      reference_lot_id: "lot-001",
      reference_hold_id: "hold-claimable-001",
      created_at: "2026-10-26T10:05:00Z",
    },
  ],
  server_time: "2026-10-26T10:15:00Z",
};

describe("WalletPage manual bid claim and Stripe top-up flows", () => {
  beforeEach(() => {
    resetClockOffset();
    useAuthStore.getState().setSession("jwt-test-token", MOCK_USER);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    useAuthStore.getState().clearSession();
    resetClockOffset();
  });

  it("renders 3 balance buckets, CLAIMABLE holds, and calls POST /api/v1/wallet/claims/{hold_id} on Claim Bid click with instant balance update", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/wallet")) {
        return Promise.resolve(
          new Response(JSON.stringify(INITIAL_WALLET_SUMMARY), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.endsWith("/api/v1/wallet/claims/hold-claimable-001")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              hold: {
                id: "hold-claimable-001",
                lot_id: "lot-001",
                lot_title: "Raf Simons AW01 Riot! Riot! Riot! Camo Bomber",
                amount: "300.00",
                status: "CLAIMED",
                created_at: "2026-10-26T10:00:00Z",
                outbid_at: "2026-10-26T10:05:00Z",
                claimed_at: "2026-10-26T10:16:00Z",
              },
              claimed_amount: "300.00",
              available_balance: "420.00",
              held_balance: "450.00",
              claimable_balance: "0.00",
              server_time: "2026-10-26T10:16:00Z",
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/wallet"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByText("Raf Simons AW01 Riot! Riot! Riot! Camo Bomber"),
      ).toBeDefined();
    });

    const availContainer = screen.getByTestId("wallet-available-balance");
    const heldContainer = screen.getByTestId("wallet-held-balance");
    const claimableContainer = screen.getByTestId("wallet-claimable-balance");

    expect(within(availContainer).getByText("$120.00")).toBeDefined();
    expect(within(heldContainer).getByText("$450.00")).toBeDefined();
    expect(within(claimableContainer).getByText("$300.00")).toBeDefined();

    const claimBidButton = screen.getByRole("button", {
      name: /Claim Bid \(\$300\.00\)/i,
    });
    fireEvent.click(claimBidButton);

    await waitFor(() => {
      expect(within(availContainer).getByText("$420.00")).toBeDefined();
      expect(within(claimableContainer).getByText("$0.00")).toBeDefined();
    });

    const calledUrls = fetchMock.mock.calls.map((call: unknown[]) =>
      String(call[0]),
    );
    expect(
      calledUrls.some((u) =>
        u.endsWith("/api/v1/wallet/claims/hold-claimable-001"),
      ),
    ).toBe(true);

    const updatedStoreUser = useAuthStore.getState().user;
    expect(updatedStoreUser?.available_balance).toBe("420.00");
    expect(updatedStoreUser?.claimable_balance).toBe("0.00");
    expect(screen.getByText("RETURNED TO AVAILABLE")).toBeDefined();
  });

  it("opens Stripe TopupModal, validates boundary USD amounts, and submits POST /api/v1/wallet/topup/checkout", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/wallet")) {
        return Promise.resolve(
          new Response(JSON.stringify(INITIAL_WALLET_SUMMARY), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.endsWith("/api/v1/wallet/topup/checkout")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              checkout_url:
                "https://checkout.stripe.com/c/pay/cs_test_vault_500",
              session_id: "cs_test_vault_500",
              server_time: "2026-10-26T10:18:00Z",
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/wallet"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /TOP UP VIA STRIPE/i }),
      ).toBeDefined();
    });

    fireEvent.click(screen.getByRole("button", { name: /TOP UP VIA STRIPE/i }));
    expect(
      screen.getByRole("dialog", { name: "STRIPE VAULT TOP-UP" }),
    ).toBeDefined();

    const amountInput = screen.getByLabelText("TOP-UP AMOUNT (USD)");
    fireEvent.change(amountInput, { target: { value: "0.001" } });
    fireEvent.click(
      screen.getByRole("button", { name: /PROCEED TO STRIPE CHECKOUT/i }),
    );
    expect(
      screen.getByText(/Enter a valid USD amount between \$0\.01/i),
    ).toBeDefined();

    fireEvent.change(amountInput, { target: { value: "500.00" } });
    fireEvent.click(
      screen.getByRole("button", { name: /PROCEED TO STRIPE CHECKOUT/i }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("stripe-checkout-session-banner")).toBeDefined();
    });
  });

  it("claims all outbid holds via POST /api/v1/wallet/claims/claim-all and displays errors on conflict", async () => {
    let shouldFailSingleClaim = true;
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/wallet")) {
        return Promise.resolve(
          new Response(JSON.stringify(INITIAL_WALLET_SUMMARY), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (
        url.endsWith("/api/v1/wallet/claims/hold-claimable-001") &&
        shouldFailSingleClaim
      ) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              error_code: "HOLD_ALREADY_CLAIMED",
              message: "Hold has already been claimed",
              details: { hold_id: "hold-claimable-001" },
              server_time: "2026-10-26T10:19:00Z",
            }),
            {
              status: 409,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      if (url.endsWith("/api/v1/wallet/claims/claim-all")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              claimed_count: 1,
              claimed_amount: "300.00",
              claimed_hold_ids: ["hold-claimable-001"],
              available_balance: "420.00",
              held_balance: "450.00",
              claimable_balance: "0.00",
              server_time: "2026-10-26T10:20:00Z",
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/wallet"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Claim Bid \(\$300\.00\)/i }),
      ).toBeDefined();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /Claim Bid \(\$300\.00\)/i }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("wallet-error-banner")).toBeDefined();
      expect(screen.getByText(/Hold has already been claimed/i)).toBeDefined();
    });

    shouldFailSingleClaim = false;
    const claimAllButtons = screen.getAllByRole("button", {
      name: /Claim All \(\$300\.00\)/i,
    });
    const firstBannerBtn = claimAllButtons[0];
    if (firstBannerBtn !== undefined) {
      fireEvent.click(firstBannerBtn);
    }

    await waitFor(() => {
      const availContainer = screen.getByTestId("wallet-available-balance");
      const claimableContainer = screen.getByTestId("wallet-claimable-balance");
      expect(within(availContainer).getByText("$420.00")).toBeDefined();
      expect(within(claimableContainer).getByText("$0.00")).toBeDefined();
      expect(screen.getByText("RETURNED TO AVAILABLE")).toBeDefined();
    });
  });

  it("renders unauthenticated access gate without API error when user session is null", async () => {
    useAuthStore.getState().clearSession();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/wallet"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("wallet-unauthenticated")).toBeDefined();
      expect(screen.getByText("AUTHENTICATION REQUIRED")).toBeDefined();
    });

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("resets TopupModal error and session state upon closing and reopening", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/wallet")) {
        return Promise.resolve(
          new Response(JSON.stringify(INITIAL_WALLET_SUMMARY), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/wallet"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /TOP UP VIA STRIPE/i }),
      ).toBeDefined();
    });

    fireEvent.click(screen.getByRole("button", { name: /TOP UP VIA STRIPE/i }));
    const amountInput = screen.getByLabelText("TOP-UP AMOUNT (USD)");
    fireEvent.change(amountInput, { target: { value: "invalid" } });
    fireEvent.click(
      screen.getByRole("button", { name: /PROCEED TO STRIPE CHECKOUT/i }),
    );

    expect(
      screen.getByText(/Enter a valid USD amount between \$0\.01/i),
    ).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: /CANCEL/i }));

    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: "STRIPE VAULT TOP-UP" }),
      ).toBeNull();
    });

    fireEvent.click(screen.getByRole("button", { name: /TOP UP VIA STRIPE/i }));
    expect(
      screen.queryByText(/Enter a valid USD amount between \$0\.01/i),
    ).toBeNull();
  });
});
