import React, { useState } from "react";
import { getServerNowMs } from "../../shared/store/clockStore";
import type {
  LotCategory,
  LotMediaItem,
  LotSpecs,
} from "../../shared/types/domain";
import { Badge } from "../../shared/ui/Badge";
import {
  ReticleFrame,
  SlashedZeroGlyph,
  UnborderedWord,
} from "../../shared/ui/BrandGlyphs";
import { Button } from "../../shared/ui/Button";
import { Card } from "../../shared/ui/Card";
import { CategorySpecsTable } from "../../shared/ui/CategorySpecsTable";
import { ClaimableHoldsBanner } from "../../shared/ui/ClaimableHoldsBanner";
import { CountdownTimer } from "../../shared/ui/CountdownTimer";
import { Input } from "../../shared/ui/Input";
import { MediaGallery } from "../../shared/ui/MediaGallery";
import { Modal } from "../../shared/ui/Modal";
import { PriceTicker } from "../../shared/ui/PriceTicker";
import { Select } from "../../shared/ui/Select";
import { SkeletonBox } from "../../shared/ui/SkeletonBox";
import { Toast } from "../../shared/ui/Toast";

const SAMPLE_SPECS_BY_CATEGORY: Record<LotCategory, LotSpecs> = {
  APPAREL: {
    category: "APPAREL",
    brand: "Raf Simons",
    season_era: "AW01 Riot! Riot! Riot!",
    tagged_size: "48",
    condition_grade: "ARCHIVAL_MINT",
    measurements_cm: {
      chest: 65,
      shoulders: 55,
      length: 71,
      sleeve: 66,
    },
    materials: ["100% Heavy Cotton", "Riri M8 Zippers"],
  },
  VINYL: {
    category: "VINYL",
    artist: "Aphex Twin",
    album_title: "Drukqs (5xLP Audiophile Box Set)",
    label: "Warp Records",
    catalog_number: "WARPLP92",
    release_year: 2001,
    country_pressing: "UK First Press",
    media_grade: "NM",
    sleeve_grade: "VG_PLUS",
    matrix_runout: "WARPLP 92 A-1 / B-1",
    rpm: 33,
  },
  HARDWARE: {
    category: "HARDWARE",
    manufacturer: "Roland",
    model_name: "TR-808 Rhythm Composer",
    production_year: 1981,
    serial_number: "105940",
    voltage: "100V_JP",
    functional_status: "FULLY_SERVICED_RECAPPED",
    included_accessories: ["Original Smoked Plexi Cover", "Service Dossier"],
  },
  ARTIFACT: {
    category: "ARTIFACT",
    creator_maker: "Dieter Rams / Braun",
    origin_period: "1987 West Germany",
    primary_material: "Matte Black Anodized Aluminum",
    dimensions_mm: {
      width: 80,
      height: 136,
      depth: 11,
      weight_grams: 115,
    },
    provenance_summary: "Kronberg Industrial Design Archive",
    authentication_code: "BRAUN-ET66-1987",
  },
};

const SAMPLE_MEDIA: ReadonlyArray<LotMediaItem> = [
  {
    id: "media-1",
    slot_type: "PRIMARY",
    public_url: "data:image/gif;base64,R0lGODlhAQABAIAAAAUEBAAAACwAAAAAAQABAAACAkQBADs=",
    mime_type: "image/jpeg",
    sort_order: 0,
  },
  {
    id: "media-2",
    slot_type: "TAG_STAMP",
    public_url: "data:image/gif;base64,R0lGODlhAQABAIAAAAUEBAAAACwAAAAAAQABAAACAkQBADs=",
    mime_type: "image/jpeg",
    sort_order: 1,
  },
  {
    id: "media-3",
    slot_type: "DEFECT",
    public_url: "data:image/gif;base64,R0lGODlhAQABAIAAAAUEBAAAACwAAAAAAQABAAACAkQBADs=",
    mime_type: "image/jpeg",
    sort_order: 2,
  },
  {
    id: "media-4",
    slot_type: "DETAIL",
    public_url: "data:image/gif;base64,R0lGODlhAQABAIAAAAUEBAAAACwAAAAAAQABAAACAkQBADs=",
    mime_type: "image/jpeg",
    sort_order: 3,
  },
];

export const KitchenSinkPage: React.FC = () => {
  const [selectedCategory, setSelectedCategory] =
    useState<LotCategory>("APPAREL");
  const [bidInput, setBidInput] = useState<string>("1850.00");
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [claimBannerClaimed, setClaimBannerClaimed] = useState<boolean>(false);
  const [showToast, setShowToast] = useState<boolean>(true);

  const antiSnipeEndsAtIso = new Date(
    getServerNowMs() + 90_000,
  ).toISOString();

  return (
    <div data-testid="kitchen-sink-page" className="flex flex-col gap-10">
      <div className="border-b border-[#262626] pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="text-xs font-mono-tech text-[#A6A6A6] uppercase mb-2">
            DESIGN SYSTEM ARCHIVE · SLICE 2 SPECIMEN VERIFICATION
          </div>
          <h1 className="text-3xl md:text-5xl font-display font-black uppercase tracking-tight text-[#F5F5F5]">
            <UnborderedWord word="ØBSØLETE KITCHEN SINK" cutoutColor="#141414" />
          </h1>
        </div>
        <div className="flex items-center gap-3">
          <SlashedZeroGlyph className="w-8 h-10 text-[#F5F5F5]" />
          <ReticleFrame
            size="md"
            bracketColor="#F5F5F5"
            className="px-3 py-1.5 text-xs font-mono-tech uppercase"
          >
            <span>0PX RADIUS · 1PX CARBON HAIRLINES</span>
          </ReticleFrame>
        </div>
      </div>

      {!claimBannerClaimed && (
        <ClaimableHoldsBanner
          claimableBalance="4200.00"
          claimableCount={2}
          isClaiming={false}
          onClaimAll={() => {
            setClaimBannerClaimed(true);
          }}
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <Card className="lg:col-span-6 flex flex-col gap-5">
          <div className="text-xs font-mono-tech uppercase text-[#A6A6A6] border-b border-[#262626] pb-2">
            01. CONTROLS, BADGES &amp; INPUTS
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="primary">PLACE BID</Button>
            <Button variant="secondary">WATCH LOT</Button>
            <Button variant="buyNow">BUY NOW $3,400</Button>
            <Button variant="danger">CANCEL LOT</Button>
            <Button variant="ghost">RESET</Button>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge tone="live">LIVE AUCTION</Badge>
            <Badge tone="endingSoon">ANTI-SNIPE &lt; 120S</Badge>
            <Badge tone="claimable">CLAIMABLE HOLD</Badge>
            <Badge tone="reserveMet">RESERVE MET</Badge>
            <Badge tone="reserveUnmet">RESERVE UNMET</Badge>
            <Badge tone="category">{selectedCategory}</Badge>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Input
              label="BID AMOUNT (USD)"
              prefixText="$"
              mono
              value={bidInput}
              onChange={(event) => {
                setBidInput(event.target.value);
              }}
            />
            <Select
              label="SPECIMEN CATEGORY"
              value={selectedCategory}
              onChange={(val) => {
                setSelectedCategory(val as LotCategory);
              }}
              options={[
                { value: "APPAREL", label: "01 / APPAREL" },
                { value: "VINYL", label: "02 / VINYL" },
                { value: "HARDWARE", label: "03 / HARDWARE" },
                { value: "ARTIFACT", label: "04 / ARTIFACT" },
              ]}
            />
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setIsModalOpen(true);
              }}
            >
              OPEN RETICLE MODAL
            </Button>
          </div>
        </Card>

        <Card className="lg:col-span-6 flex flex-col gap-5">
          <div className="text-xs font-mono-tech uppercase text-[#A6A6A6] border-b border-[#262626] pb-2">
            02. LIVE AUCTION TELEMETRY (PRICE TICKER &amp; ANTI-SNIPE TIMER)
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <PriceTicker
              amountUsd={bidInput}
              label="CURRENT HIGH BID"
              size="lg"
              highlightChange
            />
            <CountdownTimer
              endsAtIso={antiSnipeEndsAtIso}
              status="LIVE"
              antiSnipeExtensionsCount={2}
            />
          </div>
          {showToast && (
            <Toast
              id="specimen-toast-1"
              type="HOLD_BECAME_CLAIMABLE"
              title="OUTBID ALERT"
              message="Your $4,200.00 hold on Raf Simons AW01 Riot Bomber is now CLAIMABLE."
              onDismiss={() => {
                setShowToast(false);
              }}
            />
          )}
          <SkeletonBox className="h-8 w-full" lines={2} />
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-6">
          <MediaGallery media={SAMPLE_MEDIA} />
        </div>
        <div className="lg:col-span-6">
          <CategorySpecsTable
            specs={SAMPLE_SPECS_BY_CATEGORY[selectedCategory]}
          />
        </div>
      </div>

      <Modal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
        }}
        title="CONFIRM ARCHIVAL BID"
        footer={
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              setIsModalOpen(false);
            }}
          >
            ACKNOWLEDGE
          </Button>
        }
      >
        <p className="font-mono-tech text-xs">
          100% OF YOUR BID (${bidInput} USD) WILL BE LOCKED IN ACTIVE_HOLD. IF
          OUTBID, FUNDS MOVE TO CLAIMABLE AND MUST BE MANUALLY CLAIMED.
        </p>
      </Modal>
    </div>
  );
};
