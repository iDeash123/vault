import React, { useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../../shared/api/client";
import { useAuthStore } from "../../shared/store/authStore";
import type {
  LotCategory,
  LotDetail,
  LotMediaItem,
  LotSpecs,
} from "../../shared/types/domain";
import { Badge } from "../../shared/ui/Badge";
import { ReticleFrame } from "../../shared/ui/BrandGlyphs";
import { Button } from "../../shared/ui/Button";
import { Input } from "../../shared/ui/Input";
import { Select } from "../../shared/ui/Select";
import {
  MediaDropzone,
  isMediaSubmissionValid,
} from "./MediaDropzone";
import {
  SpecsFormSwitcher,
  createDefaultSpecs,
} from "./SpecsFormSwitcher";

const CATEGORY_OPTIONS = [
  { value: "APPAREL", label: "01 ARCHIVAL APPAREL" },
  { value: "VINYL", label: "02 RARE VINYL PRESSING" },
  { value: "HARDWARE", label: "03 VINTAGE HARDWARE & SYNTH" },
  { value: "ARTIFACT", label: "04 HISTORICAL & INDUSTRIAL ARTIFACT" },
];

function formatDatetimeLocal(date: Date): string {
  const pad = (n: number) => n.toString().padStart(2, "0");
  const year = String(date.getFullYear());
  const month = pad(date.getMonth() + 1);
  const day = pad(date.getDate());
  const hours = pad(date.getHours());
  const minutes = pad(date.getMinutes());
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function parsePriceInput(val: string): number {
  const cleaned = val.replace(/^\$/, "").trim();
  return parseFloat(cleaned);
}

function validateCategorySpecs(specs: LotSpecs): Record<string, string> {
  const errors: Record<string, string> = {};
  switch (specs.category) {
    case "VINYL":
      if (
        !specs.release_year ||
        !Number.isInteger(specs.release_year) ||
        specs.release_year < 1950 ||
        specs.release_year > 2026
      ) {
        errors["specs.release_year"] =
          "RELEASE YEAR MUST BE AN INTEGER BETWEEN 1950 AND 2026.";
      }
      break;
    default:
      break;
  }
  return errors;
}

export const CreateLotPage: React.FC = () => {
  const currentUser = useAuthStore((s) => s.user);

  const [category, setCategory] = useState<LotCategory>("APPAREL");
  const [title, setTitle] = useState<string>("");
  const [subtitle, setSubtitle] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [specs, setSpecs] = useState<LotSpecs>(() => createDefaultSpecs("APPAREL"));
  const [specsErrors, setSpecsErrors] = useState<Record<string, string>>({});

  const now = new Date();
  const defaultStartsAt = new Date(now.getTime() + 60 * 60 * 1000);
  const defaultEndsAt = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);

  const [startPrice, setStartPrice] = useState<string>("100.00");
  const [reservePrice, setReservePrice] = useState<string>("");
  const [buyNowPrice, setBuyNowPrice] = useState<string>("");
  const [minBidIncrement, setMinBidIncrement] = useState<string>("5.00");
  const [startsAt, setStartsAt] = useState<string>(
    formatDatetimeLocal(defaultStartsAt),
  );
  const [endsAt, setEndsAt] = useState<string>(
    formatDatetimeLocal(defaultEndsAt),
  );

  const [createdLot, setCreatedLot] = useState<LotDetail | null>(null);
  const [uploadedMedia, setUploadedMedia] = useState<LotMediaItem[]>([]);
  const [isCreatingDraft, setIsCreatingDraft] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitSuccess, setSubmitSuccess] = useState<boolean>(false);
  const [pageError, setPageError] = useState<string>("");

  const handleCategoryChange = (newCat: string) => {
    const nextCategory = newCat as LotCategory;
    setCategory(nextCategory);
    setSpecs(createDefaultSpecs(nextCategory));
    setSpecsErrors({});
  };

  const handleCreateDraft = async (e?: React.SyntheticEvent) => {
    if (e !== undefined) {
      e.preventDefault();
    }
    setPageError("");

    if (currentUser === null) {
      setPageError("AUTHENTICATION REQUIRED. PLEASE LOG IN TO CREATE A LOT.");
      return;
    }

    if (title.trim().length === 0) {
      setPageError("LOT TITLE IS REQUIRED.");
      return;
    }
    if (subtitle.trim().length === 0) {
      setPageError("LOT SUBTITLE IS REQUIRED.");
      return;
    }
    if (description.trim().length === 0) {
      setPageError("LOT DESCRIPTION IS REQUIRED.");
      return;
    }

    const startVal = parsePriceInput(startPrice);
    if (isNaN(startVal) || startVal <= 0) {
      setPageError("START PRICE MUST BE GREATER THAN $0.00.");
      return;
    }

    let resVal: number | null = null;
    if (reservePrice.trim().length > 0) {
      const parsedRes = parsePriceInput(reservePrice);
      if (isNaN(parsedRes) || parsedRes < startVal) {
        setPageError("RESERVE PRICE MUST BE GREATER THAN OR EQUAL TO START PRICE.");
        return;
      }
      resVal = parsedRes;
    }

    const incVal = parsePriceInput(minBidIncrement);
    if (isNaN(incVal) || incVal < 1.0) {
      setPageError("MINIMUM BID INCREMENT MUST BE AT LEAST $1.00.");
      return;
    }

    let buyVal: number | null = null;
    if (buyNowPrice.trim().length > 0) {
      const parsedBuy = parsePriceInput(buyNowPrice);
      const baseline = resVal !== null ? Math.max(startVal, resVal) : startVal;
      if (isNaN(parsedBuy) || parsedBuy <= baseline + incVal) {
        setPageError(
          "BUY NOW PRICE MUST EXCEED COALESCE(RESERVE, START) + MIN BID INCREMENT.",
        );
        return;
      }
      buyVal = parsedBuy;
    }

    if (startsAt.trim().length === 0) {
      setPageError("AUCTION START TIME IS REQUIRED.");
      return;
    }
    if (endsAt.trim().length === 0) {
      setPageError("AUCTION END TIME IS REQUIRED.");
      return;
    }

    const startTimestamp = new Date(startsAt).getTime();
    const endTimestamp = new Date(endsAt).getTime();
    if (isNaN(startTimestamp)) {
      setPageError("VALID AUCTION START TIME IS REQUIRED.");
      return;
    }
    if (isNaN(endTimestamp)) {
      setPageError("VALID AUCTION END TIME IS REQUIRED.");
      return;
    }
    if (endTimestamp <= startTimestamp) {
      setPageError("AUCTION END TIME MUST BE LATER THAN START TIME.");
      return;
    }

    const validationErrors = validateCategorySpecs(specs);
    if (Object.keys(validationErrors).length > 0) {
      setSpecsErrors(validationErrors);
      setPageError("PLEASE CORRECT SPECIFICATION ERRORS.");
      return;
    }
    setSpecsErrors({});

    setIsCreatingDraft(true);
    try {
      const payload = {
        category,
        title: title.trim(),
        subtitle: subtitle.trim(),
        description: description.trim(),
        specs,
        start_price: startVal.toFixed(2),
        reserve_price: resVal !== null ? resVal.toFixed(2) : null,
        buy_now_price: buyVal !== null ? buyVal.toFixed(2) : null,
        min_bid_increment: incVal.toFixed(2),
        starts_at: new Date(startsAt).toISOString(),
        ends_at: new Date(endsAt).toISOString(),
      };

      const response = await apiClient.post<LotDetail>("/lots", payload);
      setCreatedLot(response);
      setUploadedMedia(response.media);
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "FAILED TO CREATE LOT DRAFT";
      setPageError(msg);
    } finally {
      setIsCreatingDraft(false);
    }
  };

  const handleMediaUploaded = (item: LotMediaItem) => {
    setUploadedMedia((prev) => [...prev, item]);
  };

  const handleSubmitForModeration = async () => {
    if (createdLot === null) {
      setPageError("CREATE LOT DRAFT FIRST BEFORE SUBMITTING.");
      return;
    }
    if (!isMediaSubmissionValid(uploadedMedia)) {
      setPageError(
        "MINIMUM 4 MEDIA ITEMS WITH ALL 4 SLOTS (PRIMARY, TAG_STAMP, DEFECT, DETAIL) REQUIRED.",
      );
      return;
    }

    setPageError("");
    setIsSubmitting(true);
    try {
      const response = await apiClient.post<LotDetail>(
        `/lots/${createdLot.id}/submit`,
      );
      setCreatedLot(response);
      setSubmitSuccess(true);
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.message
          : "FAILED TO SUBMIT LOT FOR MODERATION";
      setPageError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      data-testid="create-lot-page"
      className="mx-auto max-w-5xl flex flex-col gap-8 py-8 px-4"
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#262626] pb-6">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono-tech text-[#A6A6A6]">
            <span>02 / CONSIGNMENT CONSTRUCTOR</span>
            <span>·</span>
            <span>AUTHENTICATED SELLER WORKSPACE</span>
          </div>
          <h1 className="text-2xl font-bold font-mono-tech uppercase tracking-wider text-[#F5F5F5] mt-1">
            CONSTRUCT ARCHIVAL LOT PASSPORT
          </h1>
        </div>
        <div className="flex items-center gap-2 font-mono-tech text-xs">
          {createdLot === null ? (
            <Badge tone="neutral">STATUS: NEW DRAFT</Badge>
          ) : submitSuccess || createdLot.status === "PENDING_REVIEW" ? (
            <Badge tone="live">STATUS: PENDING REVIEW</Badge>
          ) : (
            <Badge tone="reserveMet">STATUS: DRAFT ({createdLot.id.slice(0, 8)})</Badge>
          )}
        </div>
      </div>

      {currentUser === null && (
        <div
          data-testid="auth-required-banner"
          className="p-4 border border-[#F5F5F5] bg-[#141414] text-xs font-mono-tech text-[#F5F5F5] flex items-center justify-between"
        >
          <span>AUTHENTICATION REQUIRED: PLEASE LOG IN TO CONSIGN AN ARCHIVAL ARTIFACT.</span>
          <Link to="/login" className="underline font-bold hover:text-white">
            GO TO LOGIN
          </Link>
        </div>
      )}

      {submitSuccess && (
        <div
          data-testid="submit-success-card"
          className="border border-[#F5F5F5] bg-[#141414] p-6 flex flex-col gap-4 text-center sm:text-left"
        >
          <div className="flex items-center gap-2 text-[#F5F5F5]">
            <ReticleFrame />
            <span className="font-mono-tech text-base uppercase font-bold tracking-wider">
              LOT SUBMITTED FOR CURATOR REVIEW [PENDING_REVIEW]
            </span>
          </div>
          <p className="text-xs font-mono-tech text-[#A6A6A6]">
            Your archival consignment passport has been cryptographically registered and forwarded
            to the OBSOLETE Curatorial Committee. Once verified against our provenance database,
            it will transition to SCHEDULED / LIVE bidding.
          </p>
          <div className="flex items-center gap-3 pt-2">
            <Link
              to="/catalog"
              className="rounded-none border border-[#F5F5F5] bg-[#F5F5F5] px-4 py-2.5 text-xs font-mono-tech uppercase tracking-wider text-[#141414] hover:bg-[#D8D8D8] hover:border-[#D8D8D8] font-semibold inline-flex items-center justify-center transition-colors"
            >
              VIEW ARCHIVAL CATALOG
            </Link>
          </div>
        </div>
      )}

      {pageError.length > 0 && (
        <div
          role="alert"
          data-testid="create-lot-page-error"
          className="p-3 border border-[#F5F5F5] bg-[#141414] text-xs font-mono-tech text-[#F5F5F5]"
        >
          [ERROR] {pageError}
        </div>
      )}

      <div className="flex flex-col gap-6">
        <div className="flex items-center gap-2 border-b border-[#262626] pb-2 text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6]">
          <span>PHASE 01: ARCHIVAL CATEGORY & PASSPORT BASICS</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Select
            label="SELECT ARCHIVAL CATEGORY"
            value={category}
            options={CATEGORY_OPTIONS}
            disabled={createdLot !== null}
            onChange={handleCategoryChange}
          />
          <Input
            label="LOT TITLE"
            value={title}
            disabled={createdLot !== null}
            onChange={(e) => {
              setTitle(e.target.value);
            }}
            placeholder="e.g. Raf Simons AW01 Riot Bomber"
          />
        </div>

        <Input
          label="ARCHIVAL SUBTITLE / CATALOG CLASSIFICATION"
          value={subtitle}
          disabled={createdLot !== null}
          onChange={(e) => {
            setSubtitle(e.target.value);
          }}
          placeholder="e.g. Rare Camouflage Patch Bomber Jacket with Archival Patches"
        />

        <div className="flex flex-col gap-1.5 w-full">
          <label
            htmlFor="lot-description-input"
            className="text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6]"
          >
            CURATED PROVENANCE & CONDITION DESCRIPTION
          </label>
          <textarea
            id="lot-description-input"
            aria-label="CURATED PROVENANCE & CONDITION DESCRIPTION"
            data-testid="lot-description-input"
            rows={4}
            value={description}
            disabled={createdLot !== null}
            onChange={(e) => {
              setDescription(e.target.value);
            }}
            placeholder="Detailed historical narrative, factory codes, provenance lineage..."
            className="w-full rounded-none border border-[#262626] bg-[#141414] p-3 text-sm font-sans text-[#F5F5F5] placeholder-[#525252] focus:border-[#F5F5F5] focus:outline-none"
          />
        </div>
      </div>

      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2 border-b border-[#262626] pb-2 text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6]">
          <span>PHASE 02: CATEGORY SPECIFICATION PASSPORT</span>
        </div>
        <SpecsFormSwitcher
          category={category}
          specs={specs}
          errors={specsErrors}
          onChange={(nextSpecs) => {
            if (createdLot === null) {
              setSpecs(nextSpecs);
              if (Object.keys(specsErrors).length > 0) {
                setSpecsErrors(validateCategorySpecs(nextSpecs));
              }
            }
          }}
        />
      </div>

      <div className="flex flex-col gap-6">
        <div className="flex items-center gap-2 border-b border-[#262626] pb-2 text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6]">
          <span>PHASE 03: AUCTION PRICING & ANTI-SNIPE PARAMETERS</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
          <Input
            label="START PRICE (USD)"
            type="number"
            mono
            prefixText="$"
            value={startPrice}
            disabled={createdLot !== null}
            onChange={(e) => {
              setStartPrice(e.target.value);
            }}
            placeholder="100.00"
          />
          <Input
            label="RESERVE PRICE (OPTIONAL)"
            type="number"
            mono
            prefixText="$"
            value={reservePrice}
            disabled={createdLot !== null}
            onChange={(e) => {
              setReservePrice(e.target.value);
            }}
            placeholder="Optional"
          />
          <Input
            label="BUY NOW PRICE (OPTIONAL)"
            type="number"
            mono
            prefixText="$"
            value={buyNowPrice}
            disabled={createdLot !== null}
            onChange={(e) => {
              setBuyNowPrice(e.target.value);
            }}
            placeholder="Optional"
          />
          <Input
            label="MIN BID INCREMENT"
            type="number"
            mono
            prefixText="$"
            value={minBidIncrement}
            disabled={createdLot !== null}
            onChange={(e) => {
              setMinBidIncrement(e.target.value);
            }}
            placeholder="5.00"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="AUCTION STARTS AT (UTC)"
            type="datetime-local"
            mono
            value={startsAt}
            disabled={createdLot !== null}
            onChange={(e) => {
              setStartsAt(e.target.value);
            }}
          />
          <Input
            label="AUCTION ENDS AT (UTC)"
            type="datetime-local"
            mono
            value={endsAt}
            disabled={createdLot !== null}
            onChange={(e) => {
              setEndsAt(e.target.value);
            }}
          />
        </div>

        {createdLot === null && (
          <div className="pt-2">
            <Button
              variant="primary"
              fullWidth
              isLoading={isCreatingDraft}
              onClick={() => {
                void handleCreateDraft();
              }}
            >
              INITIALIZE ARCHIVAL LOT DRAFT & UNLOCK MEDIA UPLOAD
            </Button>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2 border-b border-[#262626] pb-2 text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6]">
          <span>PHASE 04: ARCHIVAL MEDIA UPLOAD & VERIFICATION</span>
        </div>

        <MediaDropzone
          lotId={createdLot !== null ? createdLot.id : null}
          media={uploadedMedia}
          disabled={createdLot === null || submitSuccess}
          onMediaUploaded={handleMediaUploaded}
        />
      </div>

      <div className="border-t border-[#262626] pt-6 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="text-xs font-mono-tech text-[#A6A6A6]">
          {createdLot === null ? (
            <span>STEP 1: CREATE LOT DRAFT BEFORE SUBMITTING TO CURATOR</span>
          ) : !isMediaSubmissionValid(uploadedMedia) ? (
            <span className="text-[#F5F5F5]">
              UPLOAD ALL 4 MANDATORY SLOTS (PRIMARY, TAG_STAMP, DEFECT, DETAIL) TO UNLOCK SUBMISSION
            </span>
          ) : (
            <span className="text-[#F5F5F5] font-bold">
              [CRITERIA MET] READY FOR CURATORIAL MODERATION SUBMISSION
            </span>
          )}
        </div>

        <Button
          variant="primary"
          size="lg"
          disabled={
            createdLot === null ||
            !isMediaSubmissionValid(uploadedMedia) ||
            submitSuccess ||
            isSubmitting
          }
          isLoading={isSubmitting}
          onClick={() => {
            void handleSubmitForModeration();
          }}
        >
          SUBMIT LOT FOR CURATORIAL REVIEW
        </Button>
      </div>
    </div>
  );
};
