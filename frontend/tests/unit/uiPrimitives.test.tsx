import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  resetClockOffset,
  syncWithServerTime,
} from "../../src/shared/store/clockStore";
import type {
  ApparelSpecs,
  ArtifactSpecs,
  HardwareSpecs,
  VinylSpecs,
} from "../../src/shared/types/domain";
import { CategorySpecsTable } from "../../src/shared/ui/CategorySpecsTable";
import { ClaimableHoldsBanner } from "../../src/shared/ui/ClaimableHoldsBanner";
import { CountdownTimer } from "../../src/shared/ui/CountdownTimer";

describe("UI Primitives specification suite", () => {
  beforeEach(() => {
    resetClockOffset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    resetClockOffset();
  });

  it("CountdownTimer activates ANTI-SNIPE ZONE when remaining server time is under 120s", () => {
    const serverNowIso = "2026-10-25T18:00:00.000Z";
    const serverNowMs = Date.parse(serverNowIso);
    vi.spyOn(Date, "now").mockImplementation(() => serverNowMs - 30_000);
    syncWithServerTime(serverNowIso);

    const endsInNinetySecondsIso = "2026-10-25T18:01:30.000Z";
    const { rerender } = render(
      <CountdownTimer
        endsAtIso={endsInNinetySecondsIso}
        status="LIVE"
        antiSnipeExtensionsCount={2}
      />,
    );

    const timerNode = screen.getByTestId("countdown-timer");
    expect(timerNode.getAttribute("data-anti-snipe")).toBe("true");
    expect(screen.getByText("00:01:30")).toBeDefined();
    expect(screen.getByText("ANTI-SNIPE ZONE")).toBeDefined();
    expect(screen.getByText("+2:00 EXTENDED x2")).toBeDefined();

    const endsInFiveMinutesIso = "2026-10-25T18:05:00.000Z";
    rerender(
      <CountdownTimer
        endsAtIso={endsInFiveMinutesIso}
        status="LIVE"
        antiSnipeExtensionsCount={0}
      />,
    );
    expect(timerNode.getAttribute("data-anti-snipe")).toBe("false");
    expect(screen.getByText("00:05:00")).toBeDefined();
  });

  it("CategorySpecsTable renders all 4 discriminated categories (APPAREL, VINYL, HARDWARE, ARTIFACT)", () => {
    const apparelSpecs: ApparelSpecs = {
      category: "APPAREL",
      brand: "Raf Simons",
      season_era: "AW01 Riot! Riot! Riot!",
      tagged_size: "48",
      condition_grade: "ARCHIVAL_MINT",
      measurements_cm: {
        chest: 64,
        shoulders: 54,
        length: 70,
        sleeve: 66,
      },
      materials: ["100% Cotton", "Riri Zippers"],
    };

    const vinylSpecs: VinylSpecs = {
      category: "VINYL",
      artist: "Aphex Twin",
      album_title: "Drukqs",
      label: "Warp Records",
      catalog_number: "WARPLP92",
      release_year: 2001,
      country_pressing: "UK First Press",
      media_grade: "NM",
      sleeve_grade: "VG_PLUS",
      matrix_runout: "WARPLP 92 A-1",
      rpm: 33,
    };

    const hardwareSpecs: HardwareSpecs = {
      category: "HARDWARE",
      manufacturer: "Roland",
      model_name: "TR-808",
      production_year: 1981,
      serial_number: "104892",
      voltage: "100V_JP",
      functional_status: "FULLY_SERVICED_RECAPPED",
      included_accessories: ["Original Step Cover", "Manual"],
    };

    const artifactSpecs: ArtifactSpecs = {
      category: "ARTIFACT",
      creator_maker: "Dieter Rams / Braun",
      origin_period: "1987 West Germany",
      primary_material: "Anodized Aluminum & ABS",
      dimensions_mm: {
        width: 80,
        height: 136,
        depth: 11,
        weight_grams: 115,
      },
      provenance_summary: "Frankfurt Design Archive Collection",
      authentication_code: "BRAUN-ET66-901",
    };

    const { rerender } = render(<CategorySpecsTable specs={apparelSpecs} />);
    expect(screen.getByText("Raf Simons")).toBeDefined();
    expect(screen.getByText("AW01 Riot! Riot! Riot!")).toBeDefined();

    rerender(<CategorySpecsTable specs={vinylSpecs} />);
    expect(screen.getByText("Aphex Twin")).toBeDefined();
    expect(screen.getByText("WARPLP92")).toBeDefined();
    expect(screen.getByText("33 RPM")).toBeDefined();

    rerender(<CategorySpecsTable specs={hardwareSpecs} />);
    expect(screen.getByText("Roland")).toBeDefined();
    expect(screen.getByText("TR-808")).toBeDefined();
    expect(screen.getByText("100V_JP")).toBeDefined();

    rerender(<CategorySpecsTable specs={artifactSpecs} />);
    expect(screen.getByText("Dieter Rams / Braun")).toBeDefined();
    expect(screen.getByText("BRAUN-ET66-901")).toBeDefined();
  });

  it("ClaimableHoldsBanner displays outbid balance and invokes onClaimAll when clicked", () => {
    const onClaimAllMock = vi.fn().mockResolvedValue(undefined);

    render(
      <ClaimableHoldsBanner
        claimableBalance="4200.00"
        claimableCount={2}
        onClaimAll={onClaimAllMock}
        isClaiming={false}
      />,
    );

    expect(screen.getByTestId("claimable-holds-banner")).toBeDefined();
    const claimButton = screen.getByRole("button", {
      name: /CLAIM ALL \(\$4200\.00\)/i,
    });
    fireEvent.click(claimButton);

    expect(onClaimAllMock).toHaveBeenCalledTimes(1);
  });
});
