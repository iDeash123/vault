import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiClientError, apiClient } from "../../shared/api/client";
import { useAuthStore } from "../../shared/store/authStore";
import type { AccessTokenResponse } from "../../shared/types/domain";
import { ReticleFrame, UnborderedWord } from "../../shared/ui/BrandGlyphs";
import { Button } from "../../shared/ui/Button";
import { Card } from "../../shared/ui/Card";
import { Input } from "../../shared/ui/Input";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export interface OAuthAuthorizePayload {
  authorization_url: string;
  state: string;
  provider: "GOOGLE" | "GITHUB";
  server_time: string;
}

export interface LoginPageProps {
  onExternalRedirect?: ((url: string) => void) | undefined;
}

export const LoginPage: React.FC<LoginPageProps> = ({ onExternalRedirect }) => {
  const navigate = useNavigate();
  const setSession = useAuthStore((state) => state.setSession);
  const setClaimableCount = useAuthStore((state) => state.setClaimableCount);

  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [oauthLoadingProvider, setOauthLoadingProvider] = useState<
    "google" | "github" | null
  >(null);
  const [oauthRedirectUrl, setOauthRedirectUrl] = useState<string | null>(null);

  const handleCredentialsSubmit = async () => {
    setErrorMessage("");
    const trimmedEmail = email.trim();
    if (trimmedEmail.length === 0 || password.length === 0) {
      setErrorMessage("Email and password are required.");
      return;
    }
    if (!EMAIL_PATTERN.test(trimmedEmail)) {
      setErrorMessage("Valid email and password are required.");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await apiClient.post<AccessTokenResponse>(
        "/auth/login",
        {
          email: email.trim(),
          password,
        },
      );
      setSession(response.access_token, response.user);
      if (Number(response.user.claimable_balance) > 0) {
        setClaimableCount(1);
      } else {
        setClaimableCount(0);
      }
      void navigate("/wallet");
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Authentication failed. Please verify credentials.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOAuthLogin = async (provider: "google" | "github") => {
    setErrorMessage("");
    setOauthLoadingProvider(provider);
    try {
      const response = await apiClient.get<OAuthAuthorizePayload>(
        `/auth/oauth/${provider}/authorize`,
      );
      setOauthRedirectUrl(response.authorization_url);
      if (onExternalRedirect !== undefined) {
        onExternalRedirect(response.authorization_url);
      } else if (import.meta.env.MODE !== "test") {
        window.location.assign(response.authorization_url);
      }
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage(`Unable to initialize ${provider.toUpperCase()} OAuth.`);
      }
    } finally {
      setOauthLoadingProvider(null);
    }
  };

  return (
    <div
      data-testid="login-page"
      className="mx-auto max-w-xl py-8 flex flex-col gap-6"
    >
      <Card padding="lg" className="flex flex-col gap-6">
        <div className="border-b border-[#262626] pb-4 flex flex-col gap-2">
          <span className="text-xs font-mono-tech uppercase tracking-widest text-[#A6A6A6]">
            ACCESS TERMINAL · SLICE 3.4
          </span>
          <h1 className="text-3xl font-display font-black uppercase tracking-tight text-[#F5F5F5]">
            <UnborderedWord word="AUTHENTICATE" cutoutColor="#141414" />
          </h1>
          <p className="text-xs font-sans text-[#A6A6A6]">
            Enter archival vault credentials or authenticate via verified OAuth2
            identity provider.
          </p>
        </div>

        {errorMessage.length > 0 && (
          <div
            role="alert"
            data-testid="auth-error-banner"
            className="border border-[#F5F5F5] bg-[#141414] px-4 py-3 text-xs font-mono-tech text-[#F5F5F5]"
          >
            [AUTH_REJECTED] {errorMessage}
          </div>
        )}

        {oauthRedirectUrl !== null && (
          <div
            data-testid="oauth-redirect-notice"
            className="border border-[#A6A6A6] bg-[#141414] px-4 py-2 text-xs font-mono-tech text-[#D8D8D8]"
          >
            REDIRECTING TO PROVIDER:{" "}
            <a
              data-testid="oauth-redirect-link"
              href={oauthRedirectUrl}
              className="underline text-[#F5F5F5]"
            >
              {oauthRedirectUrl}
            </a>
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void handleCredentialsSubmit();
          }}
          className="flex flex-col gap-4"
        >
          <Input
            label="EMAIL ADDRESS"
            type="email"
            placeholder="collector@obsolete.io"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
            }}
            mono
          />
          <Input
            label="PASSWORD"
            type="password"
            placeholder="••••••••••••"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
            }}
            mono
          />
          <Button
            type="submit"
            variant="primary"
            size="lg"
            fullWidth
            isLoading={isSubmitting}
          >
            SIGN IN TO VAULT
          </Button>
        </form>

        <div className="border-t border-[#262626] pt-5 flex flex-col gap-3">
          <span className="text-[11px] font-mono-tech uppercase tracking-widest text-[#525252]">
            EXTERNAL IDENTITY PROVIDERS (OAUTH 2.0)
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <ReticleFrame size="sm" bracketColor="#525252" className="w-full">
              <Button
                type="button"
                variant="secondary"
                size="md"
                fullWidth
                isLoading={oauthLoadingProvider === "google"}
                onClick={() => {
                  void handleOAuthLogin("google");
                }}
              >
                Continue with Google
              </Button>
            </ReticleFrame>
            <ReticleFrame size="sm" bracketColor="#525252" className="w-full">
              <Button
                type="button"
                variant="secondary"
                size="md"
                fullWidth
                isLoading={oauthLoadingProvider === "github"}
                onClick={() => {
                  void handleOAuthLogin("github");
                }}
              >
                Continue with GitHub
              </Button>
            </ReticleFrame>
          </div>
        </div>

        <div className="border-t border-[#262626] pt-4 flex items-center justify-between text-xs font-mono-tech text-[#A6A6A6]">
          <span>NEW ARCHIVAL COLLECTOR?</span>
          <Link
            to="/register"
            className="text-[#F5F5F5] underline uppercase hover:text-[#D8D8D8]"
          >
            REGISTER ACCOUNT ↗
          </Link>
        </div>
      </Card>
    </div>
  );
};
