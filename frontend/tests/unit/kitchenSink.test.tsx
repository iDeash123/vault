import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../../src/App";
import { apiClient } from "../../src/shared/api/client";
import { handleIncomingWsFrame } from "../../src/shared/api/wsClient";
import {
  getClockOffsetMs,
  resetClockOffset,
} from "../../src/shared/store/clockStore";
import type { LotSnapshotEvent } from "../../src/shared/types/domain";

describe("KitchenSink showcase & automatic server_time synchronization", () => {
  beforeEach(() => {
    resetClockOffset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    resetClockOffset();
  });

  it("renders KitchenSinkPage inside AppShell with all brand-book primitives", () => {
    render(
      <MemoryRouter initialEntries={["/kitchen-sink"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("kitchen-sink-page")).toBeDefined();
    expect(screen.getByTestId("price-ticker")).toBeDefined();
    expect(screen.getByTestId("countdown-timer")).toBeDefined();
    expect(screen.getByTestId("category-specs-table")).toBeDefined();
    expect(screen.getByTestId("claimable-holds-banner")).toBeDefined();
    expect(screen.getByText("Raf Simons")).toBeDefined();

    const selectNode = screen.getByLabelText("SPECIMEN CATEGORY");
    fireEvent.change(selectNode, { target: { value: "HARDWARE" } });
    expect(screen.getByText("TR-808 Rhythm Composer")).toBeDefined();
  });

  it("automatically calls syncWithServerTime when apiClient receives a REST response containing server_time", async () => {
    const fakeClientNowMs = Date.parse("2026-10-25T16:00:00.000Z");
    const serverTimeIso = "2026-10-25T16:00:25.000Z";
    vi.spyOn(Date, "now").mockReturnValue(fakeClientNowMs);

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "ok",
          server_time: serverTimeIso,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiClient.get<{ status: string; server_time: string }>(
      "/health",
    );

    expect(result.status).toBe("ok");
    expect(getClockOffsetMs()).toBe(25_000);
  });

  it("automatically calls syncWithServerTime when wsClient processes a WebSocket frame containing server_time", () => {
    const fakeClientNowMs = Date.parse("2026-10-25T16:00:00.000Z");
    const wsServerTimeIso = "2026-10-25T15:59:40.000Z";
    vi.spyOn(Date, "now").mockReturnValue(fakeClientNowMs);

    const rawFrame = JSON.stringify({
      event_type: "LOT_SNAPSHOT",
      lot_id: "00000000-0000-0000-0000-000000000001",
      status: "LIVE",
      current_price: "1450.00",
      min_valid_bid: "1500.00",
      bid_count: 7,
      leader_user_id: null,
      leader_username_masked: null,
      is_buy_now_available: false,
      is_reserve_met: true,
      ends_at: "2026-10-25T16:05:00.000Z",
      anti_snipe_extensions_count: 1,
      server_time: wsServerTimeIso,
    });

    const receivedEvents: LotSnapshotEvent[] = [];
    handleIncomingWsFrame<LotSnapshotEvent>(rawFrame, (evt) => {
      receivedEvents.push(evt);
    });

    expect(receivedEvents.length).toBe(1);
    expect(getClockOffsetMs()).toBe(-20_000);
  });
});
