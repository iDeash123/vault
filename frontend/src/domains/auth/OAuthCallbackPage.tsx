import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiClientError, apiClient } from "../../shared/api/client";
import { useAuthStore } from "../../shared/store/authStore";
import type { UserProfile } from "../../shared/types/domain";
import { Card } from "../../shared/ui/Card";
import { SkeletonBox } from "../../shared/ui/SkeletonBox";

export const OAuthCallbackPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const setAccessToken = useAuthStore((state) => state.setAccessToken);
  const setSession = useAuthStore((state) => state.setSession);
  const setClaimableCount = useAuthStore((state) => state.setClaimableCount);

  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const errorParam = searchParams.get("error");
    const errorDescription = searchParams.get("error_description");
    if (errorParam !== null && errorParam.length > 0) {
      const detail =
        errorDescription !== null && errorDescription.length > 0
          ? `${errorParam} (${errorDescription})`
          : errorParam;
      setErrorMessage(`OAuth provider returned error: ${detail}`);
      return;
    }

    const tokenParam = searchParams.get("access_token");
    if (tokenParam === null || tokenParam.trim().length === 0) {
      setErrorMessage("Missing access_token parameter in OAuth callback URL.");
      return;
    }

    const cleanToken = tokenParam.trim();
    setAccessToken(cleanToken);

    let isCancelled = false;

    const finalizeOAuthSession = async () => {
      try {
        const profile = await apiClient.get<UserProfile>(
          "/auth/me",
          undefined,
          {
            Authorization: `Bearer ${cleanToken}`,
          },
        );
        if (isCancelled) {
          return;
        }
        setSession(cleanToken, profile);
        if (Number(profile.claimable_balance) > 0) {
          setClaimableCount(1);
        } else {
          setClaimableCount(0);
        }
        void navigate("/wallet", { replace: true });
      } catch (err: unknown) {
        if (isCancelled) {
          return;
        }
        useAuthStore.getState().clearSession();
        if (err instanceof ApiClientError) {
          setErrorMessage(err.message);
        } else {
          setErrorMessage("Failed to verify OAuth session profile.");
        }
      }
    };

    void finalizeOAuthSession();

    return () => {
      isCancelled = true;
    };
  }, [navigate, searchParams, setAccessToken, setClaimableCount, setSession]);

  return (
    <div
      data-testid="oauth-callback-page"
      className="mx-auto max-w-lg py-12 flex flex-col gap-6"
    >
      <Card padding="lg" className="flex flex-col gap-4">
        <span className="text-xs font-mono-tech uppercase tracking-widest text-[#A6A6A6]">
          OAUTH 2.0 HANDSHAKE
        </span>
        {errorMessage !== null ? (
          <div className="flex flex-col gap-4">
            <div
              role="alert"
              data-testid="oauth-callback-error"
              className="border border-[#F5F5F5] bg-[#141414] px-4 py-3 text-xs font-mono-tech text-[#F5F5F5]"
            >
              [OAUTH_CALLBACK_FAILED] {errorMessage}
            </div>
            <Link
              to="/login"
              className="border border-[#F5F5F5] bg-[#F5F5F5] text-[#141414] px-4 py-2 text-xs font-mono-tech font-bold uppercase text-center"
            >
              RETURN TO LOGIN
            </Link>
          </div>
        ) : (
          <div
            data-testid="oauth-callback-loading"
            className="flex flex-col gap-3"
          >
            <p className="text-sm font-mono-tech uppercase text-[#F5F5F5]">
              SYNCHRONIZING ARCHIVAL SESSION & WALLET LEDGER...
            </p>
            <SkeletonBox className="h-10 w-full" />
          </div>
        )}
      </Card>
    </div>
  );
};
