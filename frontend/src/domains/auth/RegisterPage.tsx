import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiClientError, apiClient } from "../../shared/api/client";
import { useAuthStore } from "../../shared/store/authStore";
import type { AccessTokenResponse } from "../../shared/types/domain";
import { ReticleFrame, UnborderedWord } from "../../shared/ui/BrandGlyphs";
import { Button } from "../../shared/ui/Button";
import { Card } from "../../shared/ui/Card";
import { Input } from "../../shared/ui/Input";
import type { OAuthAuthorizePayload } from "./LoginPage";

const USERNAME_PATTERN = /^[a-zA-Z0-9_-]{3,64}$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export interface RegisterPageProps {
  onExternalRedirect?: ((url: string) => void) | undefined;
}

export const RegisterPage: React.FC<RegisterPageProps> = ({
  onExternalRedirect,
}) => {
  const navigate = useNavigate();
  const setSession = useAuthStore((state) => state.setSession);
  const setClaimableCount = useAuthStore((state) => state.setClaimableCount);

  const [email, setEmail] = useState<string>("");
  const [username, setUsername] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [bio, setBio] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [oauthLoadingProvider, setOauthLoadingProvider] = useState<
    "google" | "github" | null
  >(null);
  const [oauthRedirectUrl, setOauthRedirectUrl] = useState<string | null>(null);

  const handleRegisterSubmit = async () => {
    setErrorMessage("");
    const trimmedEmail = email.trim();
    const trimmedUsername = username.trim();

    if (
      trimmedEmail.length === 0 ||
      !EMAIL_PATTERN.test(trimmedEmail) ||
      !USERNAME_PATTERN.test(trimmedUsername) ||
      password.length < 8
    ) {
      setErrorMessage(
        "Valid email, alphanumeric username (3-64 chars), and password (min 8 chars) are required.",
      );
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await apiClient.post<AccessTokenResponse>(
        "/auth/register",
        {
          email: trimmedEmail,
          username: trimmedUsername,
          password,
          bio: bio.trim().length > 0 ? bio.trim() : null,
        },
      );
      setSession(response.access_token, response.user);
      setClaimableCount(0);
      void navigate("/wallet");
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Registration failed. Please check your inputs.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOAuthRegister = async (provider: "google" | "github") => {
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
      data-testid="register-page"
      className="mx-auto max-w-xl py-8 flex flex-col gap-6"
    >
      <Card padding="lg" className="flex flex-col gap-6">
        <div className="border-b border-[#262626] pb-4 flex flex-col gap-2">
          <span className="text-xs font-mono-tech uppercase tracking-widest text-[#A6A6A6]">
            COLLECTOR PROVISIONING · DOUBLE-ENTRY WALLET
          </span>
          <h1 className="text-3xl font-display font-black uppercase tracking-tight text-[#F5F5F5]">
            <UnborderedWord word="PROVISION" cutoutColor="#141414" />
          </h1>
          <p className="text-xs font-sans text-[#A6A6A6]">
            Registering an archival collector profile automatically provisions a
            three-bucket USD wallet ($0.00 Available / Held / Claimable).
          </p>
        </div>

        {errorMessage.length > 0 && (
          <div
            role="alert"
            data-testid="register-error-banner"
            className="border border-[#F5F5F5] bg-[#141414] px-4 py-3 text-xs font-mono-tech text-[#F5F5F5]"
          >
            [REGISTRATION_ERROR] {errorMessage}
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
            void handleRegisterSubmit();
          }}
          className="flex flex-col gap-4"
        >
          <Input
            label="EMAIL ADDRESS"
            type="email"
            placeholder="archivist@obsolete.io"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
            }}
            mono
          />
          <Input
            label="USERNAME"
            type="text"
            prefixText="@"
            placeholder="raf_collector_01"
            value={username}
            onChange={(e) => {
              setUsername(e.target.value);
            }}
            mono
          />
          <Input
            label="PASSWORD (MIN 8 CHARS)"
            type="password"
            placeholder="••••••••••••"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
            }}
            mono
          />
          <Input
            label="ARCHIVAL BIO (OPTIONAL)"
            type="text"
            placeholder="Antwerp six & early Warp Records pressings"
            value={bio}
            onChange={(e) => {
              setBio(e.target.value);
            }}
          />
          <Button
            type="submit"
            variant="primary"
            size="lg"
            fullWidth
            isLoading={isSubmitting}
          >
            CREATE COLLECTOR ACCOUNT
          </Button>
        </form>

        <div className="border-t border-[#262626] pt-5 flex flex-col gap-3">
          <span className="text-[11px] font-mono-tech uppercase tracking-widest text-[#525252]">
            INSTANT OAUTH2 PROVISIONING
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
                  void handleOAuthRegister("google");
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
                  void handleOAuthRegister("github");
                }}
              >
                Continue with GitHub
              </Button>
            </ReticleFrame>
          </div>
        </div>

        <div className="border-t border-[#262626] pt-4 flex items-center justify-between text-xs font-mono-tech text-[#A6A6A6]">
          <span>ALREADY REGISTERED?</span>
          <Link
            to="/login"
            className="text-[#F5F5F5] underline uppercase hover:text-[#D8D8D8]"
          >
            SIGN IN ↗
          </Link>
        </div>
      </Card>
    </div>
  );
};
