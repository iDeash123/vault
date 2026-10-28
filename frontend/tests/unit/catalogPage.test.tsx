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
import type { LotDetail } from "../../src/shared/types/domain";

const MOCK_APPAREL_LOT: LotDetail = {
  id: "aaaaaaaa-1111-1111-1111-111111111111",
  seller_id: "seller-111",
  leader_user_id: null,
  category: "APPAREL",
  status: "LIVE",
  title: "Raf Simons AW01 Riot Camo Bomber",
  subtitle: "Archival Camouflage Bomber Jacket",
  description: "Riot bomber with patch detail.",
  specs: {
    category: "APPAREL",
    brand: "Raf Simons",
    season_era: "AW01 Riot! Riot! Riot!",
    tagged_size: "48",
    condition_grade: "ARCHIVAL_MINT",
    measurements_cm: { chest: 58, shoulders: 50, length: 68, sleeve: 64 },
    materials: ["100% Cotton"],
  },
  start_price: "1500.00",
  reserve_price: "2000.00",
  buy_now_price: "3500.00",
  min_bid_increment: "50.00",
  current_price: "1750.00",
  min_valid_bid: "1800.00",
  bid_count: 5,
  is_buy_now_available: true,
  is_reserve_met: false,
  anti_snipe_extensions_count: 0,
  starts_at: "2026-10-25T10:00:00Z",
  ends_at: "2026-10-30T18:00:00Z",
  media: [
    {
      id: "media-1",
      slot_type: "PRIMARY",
      public_url: "http://localhost:9000/media/riot_primary.jpg",
      mime_type: "image/jpeg",
      sort_order: 0,
    },
  ],
  server_time: "2026-10-28T12:00:00Z",
};

const MOCK_VINYL_LOT: LotDetail = {
  id: "bbbbbbbb-2222-2222-2222-222222222222",
  seller_id: "seller-222",
  leader_user_id: null,
  category: "VINYL",
  status: "LIVE",
  title: "Aphex Twin - Drukqs 5xLP Box Set",
  subtitle: "WARPLP92 First Pressing Sealed",
  description: "Mint unplayed box set.",
  specs: {
    category: "VINYL",
    artist: "Aphex Twin",
    album_title: "Drukqs",
    label: "Warp Records",
    catalog_number: "WARPLP92",
    release_year: 2001,
    country_pressing: "UK First Press",
    media_grade: "M",
    sleeve_grade: "M",
    matrix_runout: "WARPLP 92 A-01",
    rpm: 33,
  },
  start_price: "600.00",
  reserve_price: null,
  buy_now_price: null,
  min_bid_increment: "25.00",
  current_price: "850.00",
  min_valid_bid: "875.00",
  bid_count: 8,
  is_buy_now_available: false,
  is_reserve_met: true,
  anti_snipe_extensions_count: 1,
  starts_at: "2026-10-25T10:00:00Z",
  ends_at: "2026-10-29T14:00:00Z",
  media: [
    {
      id: "media-2",
      slot_type: "PRIMARY",
      public_url: "http://localhost:9000/media/drukqs.jpg",
      mime_type: "image/jpeg",
      sort_order: 0,
    },
  ],
  server_time: "2026-10-28T12:00:00Z",
};

const MOCK_UNBID_LOT: LotDetail = {
  id: "cccccccc-3333-3333-3333-333333333333",
  seller_id: "seller-333",
  leader_user_id: null,
  category: "HARDWARE",
  status: "LIVE",
  title: "Roland TR-808 Rhythm Composer",
  subtitle: "Vintage Drum Machine Fully Serviced",
  description: "Mint original condition TR-808.",
  specs: {
    category: "HARDWARE",
    manufacturer: "Roland",
    model_name: "TR-808",
    production_year: 1981,
    serial_number: "SN-808-1122",
    voltage: "120V_US",
    functional_status: "FULLY_SERVICED_RECAPPED",
    included_accessories: ["Original Box"],
  },
  start_price: "4500.00",
  reserve_price: "5000.00",
  buy_now_price: null,
  min_bid_increment: "100.00",
  current_price: "0.00",
  min_valid_bid: "4500.00",
  bid_count: 0,
  is_buy_now_available: false,
  is_reserve_met: false,
  anti_snipe_extensions_count: 0,
  starts_at: "2026-10-25T10:00:00Z",
  ends_at: "2026-11-05T18:00:00Z",
  media: [],
  server_time: "2026-10-28T12:00:00Z",
};

describe("CatalogPage search, category filtering, and LotCard rendering", () => {
  beforeEach(() => {
    resetClockOffset();
    useAuthStore.getState().clearSession();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    useAuthStore.getState().clearSession();
    resetClockOffset();
  });

  it("renders live catalog grid with LotCard, CountdownTimer, PriceTicker and bids count", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/lots")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [MOCK_APPAREL_LOT, MOCK_VINYL_LOT],
              total: 2,
              limit: 50,
              offset: 0,
              server_time: "2026-10-28T12:00:00Z",
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      return Promise.reject(new Error(`Unhandled request: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/catalog"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("catalog-page")).toBeDefined();
    expect(screen.getByTestId("filter-sidebar")).toBeDefined();

    await waitFor(() => {
      expect(screen.getByTestId(`lot-card-${MOCK_APPAREL_LOT.id}`)).toBeDefined();
      expect(screen.getByTestId(`lot-card-${MOCK_VINYL_LOT.id}`)).toBeDefined();
    });

    const apparelCard = screen.getByTestId(`lot-card-${MOCK_APPAREL_LOT.id}`);
    expect(apparelCard.textContent).toContain("Raf Simons AW01 Riot Camo Bomber");
    expect(apparelCard.textContent).toContain("$1,750.00");
    expect(apparelCard.textContent).toContain("5 BIDS");
    expect(apparelCard.textContent).toContain("BUY NOW $3500.00");
    expect(apparelCard.textContent).toContain("[APPAREL]");

    const vinylCard = screen.getByTestId(`lot-card-${MOCK_VINYL_LOT.id}`);
    expect(vinylCard.textContent).toContain("Aphex Twin - Drukqs 5xLP Box Set");
    expect(vinylCard.textContent).toContain("$850.00");
    expect(vinylCard.textContent).toContain("8 BIDS");
    expect(vinylCard.textContent).toContain("[VINYL]");
  });

  it("filters catalog items by category when clicking category buttons in FilterSidebar", async () => {
    let requestedCategory: string | null = null;

    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = new URL(String(input));
      requestedCategory = url.searchParams.get("category");

      const items =
        requestedCategory === "VINYL" ? [MOCK_VINYL_LOT] : [MOCK_APPAREL_LOT, MOCK_VINYL_LOT];

      return Promise.resolve(
        new Response(
          JSON.stringify({
            items,
            total: items.length,
            limit: 50,
            offset: 0,
            server_time: "2026-10-28T12:00:00Z",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/catalog"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId(`lot-card-${MOCK_APPAREL_LOT.id}`)).toBeDefined();
    });

    const vinylFilterButton = screen.getByTestId("category-filter-vinyl");
    fireEvent.click(vinylFilterButton);

    await waitFor(() => {
      expect(requestedCategory).toBe("VINYL");
      expect(screen.queryByTestId(`lot-card-${MOCK_APPAREL_LOT.id}`)).toBeNull();
      expect(screen.getByTestId(`lot-card-${MOCK_VINYL_LOT.id}`)).toBeDefined();
    });
  });

  it("submits search query and renders empty state when no items match search filter", async () => {
    let requestedQuery: string | null = null;

    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = new URL(String(input));
      requestedQuery = url.searchParams.get("q");

      const items = requestedQuery === "NonExistentDesigner" ? [] : [MOCK_APPAREL_LOT];

      return Promise.resolve(
        new Response(
          JSON.stringify({
            items,
            total: items.length,
            limit: 50,
            offset: 0,
            server_time: "2026-10-28T12:00:00Z",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/catalog"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId(`lot-card-${MOCK_APPAREL_LOT.id}`)).toBeDefined();
    });

    const searchInput = screen.getByLabelText("FULL-TEXT CATALOG SEARCH");
    fireEvent.change(searchInput, { target: { value: "NonExistentDesigner" } });

    fireEvent.click(screen.getByRole("button", { name: "SEARCH ARCHIVE" }));

    await waitFor(() => {
      expect(requestedQuery).toBe("NonExistentDesigner");
      expect(screen.getByTestId("catalog-empty-state")).toBeDefined();
      expect(
        screen.getByText("NO SPECIMENS MATCH SPECIFIED ARCHIVAL QUERY"),
      ).toBeDefined();
    });

    fireEvent.click(screen.getByText("RESET ALL FILTERS"));

    await waitFor(() => {
      expect(screen.getByTestId(`lot-card-${MOCK_APPAREL_LOT.id}`)).toBeDefined();
    });
  });

  it("renders starting bid price for lots with zero bids and ending soon badge on active lots", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/lots")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [MOCK_UNBID_LOT, MOCK_VINYL_LOT],
              total: 2,
              limit: 50,
              offset: 0,
              server_time: "2026-10-28T12:00:00Z",
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      return Promise.reject(new Error(`Unhandled request: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/catalog"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId(`lot-card-${MOCK_UNBID_LOT.id}`)).toBeDefined();
      expect(screen.getByTestId(`lot-card-${MOCK_VINYL_LOT.id}`)).toBeDefined();
    });

    const unbidCard = screen.getByTestId(`lot-card-${MOCK_UNBID_LOT.id}`);
    expect(unbidCard.textContent).toContain("STARTING BID");
    expect(unbidCard.textContent).toContain("$4,500.00");
    expect(unbidCard.textContent).toContain("0 BIDS");
    expect(unbidCard.textContent).not.toContain("$0.00");

    const vinylCard = screen.getByTestId(`lot-card-${MOCK_VINYL_LOT.id}`);
    expect(vinylCard.textContent).toContain("ENDING SOON");
  });

  it("prevents dispatching invalid price queries when minPrice exceeds maxPrice", async () => {
    const fetchMock = vi.fn().mockImplementation(() => {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            items: [MOCK_APPAREL_LOT],
            total: 1,
            limit: 50,
            offset: 0,
            server_time: "2026-10-28T12:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/catalog"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId(`lot-card-${MOCK_APPAREL_LOT.id}`)).toBeDefined();
    });

    const minInput = screen.getByLabelText("MIN");
    const maxInput = screen.getByLabelText("MAX");

    fireEvent.change(minInput, { target: { value: "500" } });
    fireEvent.change(maxInput, { target: { value: "100" } });

    await waitFor(() => {
      const errorAlert = screen.getByTestId("catalog-error-alert");
      expect(errorAlert.textContent).toContain("MIN PRICE CANNOT EXCEED MAX PRICE");
    });
  });

  it("renders ReticleFrame inside selected category filter button and moves it when selection changes", async () => {
    const fetchMock = vi.fn().mockImplementation(() => {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            items: [MOCK_APPAREL_LOT],
            total: 1,
            limit: 50,
            offset: 0,
            server_time: "2026-10-28T12:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/catalog"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("category-filter-all")).toBeDefined();
    });

    const allButton = screen.getByTestId("category-filter-all");
    const vinylButton = screen.getByTestId("category-filter-vinyl");

    expect(allButton.querySelectorAll("svg").length).toBeGreaterThan(0);
    expect(vinylButton.querySelectorAll("svg").length).toBe(0);

    fireEvent.click(vinylButton);

    await waitFor(() => {
      expect(allButton.querySelectorAll("svg").length).toBe(0);
      expect(vinylButton.querySelectorAll("svg").length).toBeGreaterThan(0);
    });
  });

  it("ignores out-of-order stale fetch responses using requestIdRef counter", async () => {
    let resolveFirstRequest!: (res: Response) => void;
    let requestCount = 0;

    const fetchMock = vi.fn().mockImplementation(() => {
      requestCount++;
      if (requestCount === 1) {
        return new Promise<Response>((resolve) => {
          resolveFirstRequest = resolve;
        });
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            items: [MOCK_VINYL_LOT],
            total: 1,
            limit: 50,
            offset: 0,
            server_time: "2026-10-28T12:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/catalog"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    const vinylButton = screen.getByTestId("category-filter-vinyl");
    fireEvent.click(vinylButton);

    await waitFor(() => {
      expect(screen.getByTestId(`lot-card-${MOCK_VINYL_LOT.id}`)).toBeDefined();
    });

    resolveFirstRequest(
      new Response(
        JSON.stringify({
          items: [MOCK_APPAREL_LOT],
          total: 1,
          limit: 50,
          offset: 0,
          server_time: "2026-10-28T12:00:00Z",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await new Promise((r) => setTimeout(r, 50));

    expect(screen.getByTestId(`lot-card-${MOCK_VINYL_LOT.id}`)).toBeDefined();
    expect(screen.queryByTestId(`lot-card-${MOCK_APPAREL_LOT.id}`)).toBeNull();
  });
});
