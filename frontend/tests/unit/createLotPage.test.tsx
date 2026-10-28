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
import type { LotDetail, UserProfile } from "../../src/shared/types/domain";

const MOCK_SELLER: UserProfile = {
  id: "22222222-2222-2222-2222-222222222222",
  email: "seller@obsolete.io",
  username: "archival_vault",
  role: "MEMBER",
  is_active: true,
  avatar_url: null,
  bio: "Consignor of rare archival artifacts",
  available_balance: "1000.00",
  held_balance: "0.00",
  claimable_balance: "0.00",
};

const MOCK_CREATED_DRAFT: LotDetail = {
  id: "33333333-3333-3333-3333-333333333333",
  seller_id: MOCK_SELLER.id,
  leader_user_id: null,
  category: "APPAREL",
  status: "DRAFT",
  title: "Raf Simons AW01 Riot Camo Bomber",
  subtitle: "Archival Camouflage Bomber Jacket",
  description: "Authentic AW01 Riot bomber jacket in gently worn condition.",
  specs: {
    category: "APPAREL",
    brand: "Raf Simons",
    season_era: "AW01 Riot! Riot! Riot!",
    tagged_size: "48",
    condition_grade: "GENTLY_WORN",
    measurements_cm: {
      chest: 58,
      shoulders: 50,
      length: 68,
      sleeve: 64,
    },
    materials: ["100% Cotton", "Riri Zippers"],
  },
  start_price: "1500.00",
  reserve_price: "2000.00",
  buy_now_price: "3500.00",
  min_bid_increment: "50.00",
  current_price: "1500.00",
  min_valid_bid: "1500.00",
  bid_count: 0,
  is_buy_now_available: true,
  is_reserve_met: false,
  anti_snipe_extensions_count: 0,
  starts_at: "2026-11-01T12:00:00Z",
  ends_at: "2026-11-08T12:00:00Z",
  media: [],
  server_time: "2026-10-28T12:00:00Z",
};

describe("CreateLotPage consignment and media slot validation flows", () => {
  beforeEach(() => {
    resetClockOffset();
    useAuthStore.getState().setSession("jwt-seller-token", MOCK_SELLER);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    useAuthStore.getState().clearSession();
    resetClockOffset();
  });

  it("switches category specs form fields when toggling category from APPAREL to VINYL and others", async () => {
    render(
      <MemoryRouter initialEntries={["/lots/new"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("create-lot-page")).toBeDefined();
    expect(screen.getByTestId("specs-form-apparel")).toBeDefined();
    expect(screen.getByLabelText("BRAND / DESIGNER")).toBeDefined();
    expect(screen.getByLabelText("TAGGED SIZE")).toBeDefined();

    const categorySelect = screen.getByLabelText("SELECT ARCHIVAL CATEGORY");
    fireEvent.change(categorySelect, { target: { value: "VINYL" } });

    await waitFor(() => {
      expect(screen.queryByTestId("specs-form-apparel")).toBeNull();
      expect(screen.getByTestId("specs-form-vinyl")).toBeDefined();
    });

    expect(screen.getByLabelText("ARTIST")).toBeDefined();
    expect(screen.getByLabelText("ALBUM TITLE")).toBeDefined();
    expect(screen.getByLabelText("SPEED (RPM)")).toBeDefined();

    fireEvent.change(categorySelect, { target: { value: "HARDWARE" } });
    await waitFor(() => {
      expect(screen.getByTestId("specs-form-hardware")).toBeDefined();
    });
    expect(screen.getByLabelText("MANUFACTURER")).toBeDefined();
    expect(screen.getByLabelText("OPERATING VOLTAGE")).toBeDefined();

    fireEvent.change(categorySelect, { target: { value: "ARTIFACT" } });
    await waitFor(() => {
      expect(screen.getByTestId("specs-form-artifact")).toBeDefined();
    });
    expect(screen.getByLabelText("CREATOR / MAKER")).toBeDefined();
    expect(screen.getByLabelText("PRIMARY MATERIAL")).toBeDefined();
  });

  it("validates mandatory pricing constraints on draft creation", async () => {
    render(
      <MemoryRouter initialEntries={["/lots/new"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    fireEvent.click(
      screen.getByText("INITIALIZE ARCHIVAL LOT DRAFT & UNLOCK MEDIA UPLOAD"),
    );

    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert.textContent).toContain("LOT TITLE IS REQUIRED");
    });

    fireEvent.change(screen.getByLabelText("LOT TITLE"), {
      target: { value: "Test Artifact" },
    });
    fireEvent.change(
      screen.getByLabelText("ARCHIVAL SUBTITLE / CATALOG CLASSIFICATION"),
      { target: { value: "Test Subtitle" } },
    );
    fireEvent.change(
      screen.getByLabelText("CURATED PROVENANCE & CONDITION DESCRIPTION"),
      { target: { value: "Test detailed description" } },
    );

    fireEvent.change(screen.getByLabelText("START PRICE (USD)"), {
      target: { value: "200.00" },
    });
    fireEvent.change(screen.getByLabelText("RESERVE PRICE (OPTIONAL)"), {
      target: { value: "100.00" },
    });

    fireEvent.click(
      screen.getByText("INITIALIZE ARCHIVAL LOT DRAFT & UNLOCK MEDIA UPLOAD"),
    );

    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert.textContent).toContain(
        "RESERVE PRICE MUST BE GREATER THAN OR EQUAL TO START PRICE",
      );
    });
  });

  it("creates draft, enforces 4 mandatory media slots, and submits to curator review", async () => {
    let uploadedCount = 0;
    const mediaSlots = ["PRIMARY", "TAG_STAMP", "DEFECT", "DETAIL"];

    const fetchMock = vi.fn().mockImplementation((input: string | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/api/v1/lots") && init?.method === "POST") {
        return Promise.resolve(
          new Response(JSON.stringify(MOCK_CREATED_DRAFT), {
            status: 201,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url.includes("/api/v1/lots/33333333-3333-3333-3333-333333333333/media") && init?.method === "POST") {
        const currentSlot = mediaSlots[uploadedCount] ?? "DETAIL";
        uploadedCount += 1;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: `media-uuid-${String(uploadedCount)}`,
              lot_id: MOCK_CREATED_DRAFT.id,
              slot_type: currentSlot,
              storage_key: `lots/${MOCK_CREATED_DRAFT.id}/${String(uploadedCount)}.jpg`,
              public_url: `http://localhost:9000/media/${String(uploadedCount)}.jpg`,
              mime_type: "image/jpeg",
              size_bytes: 102400,
              sort_order: uploadedCount,
              server_time: "2026-10-28T12:00:00Z",
            }),
            {
              status: 201,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }

      if (url.endsWith("/api/v1/lots/33333333-3333-3333-3333-333333333333/submit") && init?.method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...MOCK_CREATED_DRAFT,
              status: "PENDING_REVIEW",
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
      <MemoryRouter initialEntries={["/lots/new"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText("LOT TITLE"), {
      target: { value: "Raf Simons AW01 Riot Camo Bomber" },
    });
    fireEvent.change(
      screen.getByLabelText("ARCHIVAL SUBTITLE / CATALOG CLASSIFICATION"),
      { target: { value: "Archival Camouflage Bomber Jacket" } },
    );
    fireEvent.change(
      screen.getByLabelText("CURATED PROVENANCE & CONDITION DESCRIPTION"),
      { target: { value: "Authentic AW01 Riot bomber jacket in gently worn condition." } },
    );
    fireEvent.change(screen.getByLabelText("START PRICE (USD)"), {
      target: { value: "1500.00" },
    });
    fireEvent.change(screen.getByLabelText("MIN BID INCREMENT"), {
      target: { value: "50.00" },
    });

    const submitCuratorButton = screen.getByRole("button", {
      name: "SUBMIT LOT FOR CURATORIAL REVIEW",
    });
    expect(submitCuratorButton.hasAttribute("disabled")).toBe(true);

    fireEvent.click(
      screen.getByText("INITIALIZE ARCHIVAL LOT DRAFT & UNLOCK MEDIA UPLOAD"),
    );

    await waitFor(() => {
      expect(screen.getByText(/STATUS: DRAFT/)).toBeDefined();
    });

    expect(submitCuratorButton.hasAttribute("disabled")).toBe(true);

    const fileInput = screen.getByTestId("media-file-input");
    const targetSlotSelect = screen.getByLabelText("SELECT TARGET SLOT FOR UPLOAD");

    const testFile = new File(["fake_photo_data"], "photo.jpg", {
      type: "image/jpeg",
    });

    fireEvent.change(targetSlotSelect, { target: { value: "PRIMARY" } });
    fireEvent.change(fileInput, { target: { files: [testFile] } });
    await waitFor(() => {
      const summary = screen.getByTestId("media-status-summary");
      expect(summary.textContent).toContain("MISSING MANDATORY SLOTS");
    });
    expect(submitCuratorButton.hasAttribute("disabled")).toBe(true);

    fireEvent.change(targetSlotSelect, { target: { value: "TAG_STAMP" } });
    fireEvent.change(fileInput, { target: { files: [testFile] } });
    await waitFor(() => {
      const summary = screen.getByTestId("media-status-summary");
      expect(summary.textContent).toContain("TAG_STAMP");
    });
    expect(submitCuratorButton.hasAttribute("disabled")).toBe(true);

    fireEvent.change(targetSlotSelect, { target: { value: "DEFECT" } });
    fireEvent.change(fileInput, { target: { files: [testFile] } });
    await waitFor(() => {
      const summary = screen.getByTestId("media-status-summary");
      expect(summary.textContent).toContain("DEFECT");
    });
    expect(submitCuratorButton.hasAttribute("disabled")).toBe(true);

    fireEvent.change(targetSlotSelect, { target: { value: "DETAIL" } });
    fireEvent.change(fileInput, { target: { files: [testFile] } });

    await waitFor(() => {
      const summary = screen.getByTestId("media-status-summary");
      expect(summary.textContent).toContain("ALL 4 MANDATORY SLOTS SATISFIED");
      expect(submitCuratorButton.hasAttribute("disabled")).toBe(false);
    });

    fireEvent.click(submitCuratorButton);

    await waitFor(() => {
      expect(screen.getByTestId("submit-success-card")).toBeDefined();
      expect(screen.getByText("STATUS: PENDING REVIEW")).toBeDefined();
    });
  });

  it("sanitizes dollar prefixed price inputs and validates required start and end times", async () => {
    render(
      <MemoryRouter initialEntries={["/lots/new"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText("LOT TITLE"), {
      target: { value: "Raf Simons AW01 Bomber" },
    });
    fireEvent.change(
      screen.getByLabelText("ARCHIVAL SUBTITLE / CATALOG CLASSIFICATION"),
      { target: { value: "Archival Riot Bomber" } },
    );
    fireEvent.change(
      screen.getByLabelText("CURATED PROVENANCE & CONDITION DESCRIPTION"),
      { target: { value: "Full description of museum condition artifact." } },
    );

    fireEvent.change(screen.getByLabelText("START PRICE (USD)"), {
      target: { value: "500.00" },
    });
    fireEvent.change(screen.getByLabelText("MIN BID INCREMENT"), {
      target: { value: "25.00" },
    });

    fireEvent.change(screen.getByLabelText("AUCTION STARTS AT (UTC)"), {
      target: { value: "" },
    });

    fireEvent.click(
      screen.getByText("INITIALIZE ARCHIVAL LOT DRAFT & UNLOCK MEDIA UPLOAD"),
    );

    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert.textContent).toContain("AUCTION START TIME IS REQUIRED");
    });
  });

  it("automatically advances target slot to next missing slot upon photo upload", async () => {
    let uploadedSlot: string | null = null;
    const fetchMock = vi.fn().mockImplementation((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/lots") && init?.method === "POST") {
        return Promise.resolve(
          new Response(JSON.stringify(MOCK_CREATED_DRAFT), {
            status: 201,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.includes("/media") && init?.method === "POST") {
        uploadedSlot = "PRIMARY";
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: "media-uuid-1",
              lot_id: MOCK_CREATED_DRAFT.id,
              slot_type: "PRIMARY",
              storage_key: "lots/photo.jpg",
              public_url: "http://localhost:9000/media/photo.jpg",
              mime_type: "image/jpeg",
              size_bytes: 102400,
              sort_order: 1,
              server_time: "2026-10-28T12:00:00Z",
            }),
            { status: 201, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      return Promise.reject(new Error(`Unhandled request: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/lots/new"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText("LOT TITLE"), {
      target: { value: "Raf Simons AW01 Bomber" },
    });
    fireEvent.change(
      screen.getByLabelText("ARCHIVAL SUBTITLE / CATALOG CLASSIFICATION"),
      { target: { value: "Archival Riot Bomber" } },
    );
    fireEvent.change(
      screen.getByLabelText("CURATED PROVENANCE & CONDITION DESCRIPTION"),
      { target: { value: "Museum condition specimen." } },
    );

    fireEvent.click(
      screen.getByText("INITIALIZE ARCHIVAL LOT DRAFT & UNLOCK MEDIA UPLOAD"),
    );

    await waitFor(() => {
      expect(screen.getByText(/STATUS: DRAFT/)).toBeDefined();
    });

    const fileInput = screen.getByTestId("media-file-input");
    const targetSlotSelect = screen.getByLabelText<HTMLSelectElement>(
      "SELECT TARGET SLOT FOR UPLOAD",
    );
    expect(targetSlotSelect.value).toBe("PRIMARY");

    const testFile = new File(["bytes"], "primary.jpg", { type: "image/jpeg" });
    fireEvent.change(fileInput, { target: { files: [testFile] } });

    await waitFor(() => {
      expect(uploadedSlot).toBe("PRIMARY");
      expect(targetSlotSelect.value).toBe("TAG_STAMP");
    });
  });

  it("preserves trailing comma and space during incremental typing in materials input", async () => {
    let capturedPayload: { specs?: { materials?: string[] } } | null = null;
    const fetchMock = vi.fn().mockImplementation((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (
        url.endsWith("/api/v1/lots") &&
        init?.method === "POST" &&
        typeof init.body === "string"
      ) {
        capturedPayload = JSON.parse(init.body) as {
          specs?: { materials?: string[] };
        };
        return Promise.resolve(
          new Response(JSON.stringify(MOCK_CREATED_DRAFT), {
            status: 201,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return Promise.reject(new Error(`Unhandled request: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/lots/new"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    const materialsInput = screen.getByLabelText<HTMLInputElement>(
      "MATERIALS (COMMA-SEPARATED)",
    );

    fireEvent.change(materialsInput, {
      target: { value: "100% Cotton" },
    });
    expect(materialsInput.value).toBe("100% Cotton");

    fireEvent.change(materialsInput, {
      target: { value: "100% Cotton," },
    });
    expect(materialsInput.value).toBe("100% Cotton,");

    fireEvent.change(materialsInput, {
      target: { value: "100% Cotton, " },
    });
    expect(materialsInput.value).toBe("100% Cotton, ");

    fireEvent.change(materialsInput, {
      target: { value: "100% Cotton, Riri Zippers" },
    });
    expect(materialsInput.value).toBe("100% Cotton, Riri Zippers");

    fireEvent.change(screen.getByLabelText("LOT TITLE"), {
      target: { value: "Raf Simons AW01 Bomber" },
    });
    fireEvent.change(
      screen.getByLabelText("ARCHIVAL SUBTITLE / CATALOG CLASSIFICATION"),
      { target: { value: "Archival Riot Bomber" } },
    );
    fireEvent.change(
      screen.getByLabelText("CURATED PROVENANCE & CONDITION DESCRIPTION"),
      { target: { value: "Museum condition specimen." } },
    );

    fireEvent.click(
      screen.getByText("INITIALIZE ARCHIVAL LOT DRAFT & UNLOCK MEDIA UPLOAD"),
    );

    await waitFor(() => {
      expect(capturedPayload).not.toBeNull();
      expect(capturedPayload?.specs?.materials).toEqual([
        "100% Cotton",
        "Riri Zippers",
      ]);
    });
  });

  it("validates vinyl release_year between 1950 and 2026 and wires errors to SpecsFormSwitcher", async () => {
    render(
      <MemoryRouter initialEntries={["/lots/new"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText("SELECT ARCHIVAL CATEGORY"), {
      target: { value: "VINYL" },
    });

    await waitFor(() => {
      expect(screen.getByTestId("specs-form-vinyl")).toBeDefined();
    });

    fireEvent.change(screen.getByLabelText("LOT TITLE"), {
      target: { value: "Aphex Twin - Drukqs" },
    });
    fireEvent.change(
      screen.getByLabelText("ARCHIVAL SUBTITLE / CATALOG CLASSIFICATION"),
      { target: { value: "Box Set 5xLP" } },
    );
    fireEvent.change(
      screen.getByLabelText("CURATED PROVENANCE & CONDITION DESCRIPTION"),
      { target: { value: "Archival collector copy." } },
    );

    const releaseYearInput = screen.getByLabelText("RELEASE YEAR");
    fireEvent.change(releaseYearInput, { target: { value: "1920" } });

    fireEvent.click(
      screen.getByText("INITIALIZE ARCHIVAL LOT DRAFT & UNLOCK MEDIA UPLOAD"),
    );

    await waitFor(() => {
      const alert = screen.getByTestId("create-lot-page-error");
      expect(alert.textContent).toContain("PLEASE CORRECT SPECIFICATION ERRORS");
      expect(
        screen.getByText(/RELEASE YEAR MUST BE AN INTEGER BETWEEN 1950 AND 2026/i),
      ).toBeDefined();
    });

    fireEvent.change(releaseYearInput, { target: { value: "2001" } });
    await waitFor(() => {
      expect(
        screen.queryByText(/RELEASE YEAR MUST BE AN INTEGER BETWEEN 1950 AND 2026/i),
      ).toBeNull();
    });
  });
});
