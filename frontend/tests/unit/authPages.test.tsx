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

describe("LoginPage, RegisterPage, and OAuthCallbackPage authentication flows", () => {
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

  it("renders Google and GitHub OAuth2 buttons on LoginPage and initiates OAuth authorize handshake", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/auth/oauth/google/authorize")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              authorization_url:
                "https://accounts.google.com/o/oauth2/v2/auth?state=google_state_123",
              state: "google_state_123",
              provider: "GOOGLE",
              server_time: "2026-10-26T10:20:00Z",
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      if (url.includes("/api/v1/auth/oauth/github/authorize")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              authorization_url:
                "https://github.com/login/oauth/authorize?state=github_state_456",
              state: "github_state_456",
              provider: "GITHUB",
              server_time: "2026-10-26T10:20:05Z",
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
      <MemoryRouter initialEntries={["/login"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    const googleButton = screen.getByRole("button", {
      name: /Continue with Google/i,
    });
    const githubButton = screen.getByRole("button", {
      name: /Continue with GitHub/i,
    });

    expect(googleButton).toBeDefined();
    expect(githubButton).toBeDefined();

    fireEvent.click(googleButton);

    await waitFor(() => {
      const link = screen.getByTestId("oauth-redirect-link");
      expect(link.getAttribute("href")).toContain(
        "https://accounts.google.com/o/oauth2/v2/auth?state=google_state_123",
      );
    });

    fireEvent.click(githubButton);

    await waitFor(() => {
      const link = screen.getByTestId("oauth-redirect-link");
      expect(link.getAttribute("href")).toContain(
        "https://github.com/login/oauth/authorize?state=github_state_456",
      );
    });
  });

  it("processes OAuthCallbackPage redirect with access_token, hydrates authStore via /auth/me, and navigates to /wallet", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/me")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: "22222222-2222-2222-2222-222222222222",
              email: "oauth_archivist@obsolete.io",
              username: "oauth_archivist",
              role: "MEMBER",
              is_active: true,
              avatar_url: "https://example.com/avatar.png",
              bio: null,
              available_balance: "750.00",
              held_balance: "0.00",
              claimable_balance: "150.00",
              server_time: "2026-10-26T10:25:00Z",
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      if (url.endsWith("/api/v1/wallet")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              available_balance: "750.00",
              held_balance: "0.00",
              claimable_balance: "150.00",
              holds: [],
              ledger_entries: [],
              server_time: "2026-10-26T10:25:01Z",
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
      <MemoryRouter
        initialEntries={["/auth/callback?access_token=oauth_jwt_token_xyz"]}
      >
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("wallet-page")).toBeDefined();
    });

    const authState = useAuthStore.getState();
    expect(authState.isAuthenticated).toBe(true);
    expect(authState.accessToken).toBe("oauth_jwt_token_xyz");
    expect(authState.user?.username).toBe("oauth_archivist");
    expect(authState.user?.available_balance).toBe("750.00");
    expect(authState.user?.claimable_balance).toBe("150.00");
  });

  it("displays an error alert on OAuthCallbackPage when access_token is missing or provider returns error", async () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={["/auth/callback"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("oauth-callback-error")).toBeDefined();
      expect(
        screen.getByText(/Missing access_token parameter/i),
      ).toBeDefined();
    });
    unmount();

    render(
      <MemoryRouter
        initialEntries={[
          "/auth/callback?error=access_denied&error_description=User+denied+scope",
        ]}
      >
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("oauth-callback-error")).toBeDefined();
      expect(
        screen.getByText(/access_denied \(User denied scope\)/i),
      ).toBeDefined();
    });
  });

  it("validates empty credentials and displays API error on invalid LoginPage submission", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/login")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              error_code: "INVALID_CREDENTIALS",
              message: "Invalid email or password",
              details: {},
              server_time: "2026-10-26T10:28:00Z",
            }),
            {
              status: 401,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/login"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /SIGN IN TO VAULT/i }));
    expect(screen.getByTestId("auth-error-banner")).toBeDefined();
    expect(
      screen.getByText(/Email and password are required/i),
    ).toBeDefined();

    fireEvent.change(screen.getByLabelText("EMAIL ADDRESS"), {
      target: { value: "wrong@obsolete.io" },
    });
    fireEvent.change(screen.getByLabelText("PASSWORD"), {
      target: { value: "WrongPassword123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /SIGN IN TO VAULT/i }));

    await waitFor(() => {
      expect(screen.getByText(/Invalid email or password/i)).toBeDefined();
    });
  });

  it("submits RegisterPage credential form, validates inputs, hydrates session, and supports AppShell logout", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/register")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              access_token: "reg_jwt_token_001",
              user: {
                id: "33333333-3333-3333-3333-333333333333",
                email: "new_archivist@obsolete.io",
                username: "new_archivist",
                role: "MEMBER",
                is_active: true,
                avatar_url: null,
                bio: "Synth collector",
                available_balance: "0.00",
                held_balance: "0.00",
                claimable_balance: "0.00",
              },
              server_time: "2026-10-26T10:30:00Z",
            }),
            {
              status: 201,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      if (url.endsWith("/api/v1/wallet")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              available_balance: "0.00",
              held_balance: "0.00",
              claimable_balance: "0.00",
              holds: [],
              ledger_entries: [],
              server_time: "2026-10-26T10:30:01Z",
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      if (url.endsWith("/api/v1/auth/logout")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              status: "logged_out",
              server_time: "2026-10-26T10:31:00Z",
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
      <MemoryRouter initialEntries={["/register"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText("EMAIL ADDRESS"), {
      target: { value: "new_archivist@obsolete.io" },
    });
    fireEvent.change(screen.getByLabelText("USERNAME"), {
      target: { value: "bad space!" },
    });
    fireEvent.change(screen.getByLabelText("PASSWORD (MIN 8 CHARS)"), {
      target: { value: "short" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /CREATE COLLECTOR ACCOUNT/i }),
    );
    expect(screen.getByTestId("register-error-banner")).toBeDefined();

    fireEvent.change(screen.getByLabelText("USERNAME"), {
      target: { value: "new_archivist" },
    });
    fireEvent.change(screen.getByLabelText("PASSWORD (MIN 8 CHARS)"), {
      target: { value: "StrongVaultPassword!23" },
    });

    fireEvent.click(
      screen.getByRole("button", { name: /CREATE COLLECTOR ACCOUNT/i }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("wallet-page")).toBeDefined();
    });

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().user?.username).toBe("new_archivist");

    const logoutBtn = screen.getByRole("button", { name: /LOGOUT/i });
    fireEvent.click(logoutBtn);

    await waitFor(() => {
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
      expect(useAuthStore.getState().user).toBeNull();
    });
  });

  it("renders Google and GitHub OAuth buttons on RegisterPage and shows redirect link", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/auth/oauth/google/authorize")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              authorization_url:
                "https://accounts.google.com/o/oauth2/v2/auth?state=reg_google_123",
              state: "reg_google_123",
              provider: "GOOGLE",
              server_time: "2026-10-26T10:40:00Z",
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
      <MemoryRouter initialEntries={["/register"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    const googleBtn = screen.getByRole("button", {
      name: /Continue with Google/i,
    });
    fireEvent.click(googleBtn);

    await waitFor(() => {
      const link = screen.getByTestId("oauth-redirect-link");
      expect(link.getAttribute("href")).toContain("reg_google_123");
    });
  });

  it("clears auth store when OAuthCallbackPage fails to fetch profile from /auth/me", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/me")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              error_code: "INVALID_TOKEN",
              message: "Token has expired or is invalid",
              details: {},
              server_time: "2026-10-26T10:45:00Z",
            }),
            {
              status: 401,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter
        initialEntries={["/auth/callback?access_token=bad_jwt_token_123"]}
      >
        <AppRoutes />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("oauth-callback-error")).toBeDefined();
    });

    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});
