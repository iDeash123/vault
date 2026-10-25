import React, { useState } from "react";
import type { LotMediaItem, MediaSlotType } from "../types/domain";
import { ReticleFrame } from "./BrandGlyphs";

export interface MediaGalleryProps {
  media: ReadonlyArray<LotMediaItem>;
}

const SLOT_FILTERS: ReadonlyArray<"ALL" | MediaSlotType> = [
  "ALL",
  "PRIMARY",
  "TAG_STAMP",
  "DEFECT",
  "DETAIL",
];

export const MediaGallery: React.FC<MediaGalleryProps> = ({ media }) => {
  const sortedMedia = [...media].sort((a, b) => a.sort_order - b.sort_order);
  const [selectedSlot, setSelectedSlot] = useState<"ALL" | MediaSlotType>("ALL");
  const [activeIndex, setActiveIndex] = useState<number>(0);
  const [isZoomed, setIsZoomed] = useState<boolean>(false);

  const filteredMedia =
    selectedSlot === "ALL"
      ? sortedMedia
      : sortedMedia.filter((item) => item.slot_type === selectedSlot);

  const currentItem =
    filteredMedia[activeIndex] ?? filteredMedia[0] ?? sortedMedia[0];

  return (
    <div className="flex flex-col gap-4 border border-[#262626] bg-[#141414] p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#262626] pb-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {SLOT_FILTERS.map((slot) => {
            const isActive = selectedSlot === slot;
            return (
              <button
                key={slot}
                type="button"
                onClick={() => {
                  setSelectedSlot(slot);
                  setActiveIndex(0);
                }}
                className={`rounded-none border px-2.5 py-1 text-[11px] font-mono-tech uppercase tracking-wider ${
                  isActive
                    ? "border-[#F5F5F5] bg-[#F5F5F5] text-[#141414] font-semibold"
                    : "border-[#262626] bg-[#141414] text-[#A6A6A6] hover:border-[#F5F5F5]"
                }`}
              >
                {slot}
              </button>
            );
          })}
        </div>
        <button
          type="button"
          onClick={() => {
            setIsZoomed((prev) => !prev);
          }}
          className="rounded-none border border-[#262626] px-2.5 py-1 text-[11px] font-mono-tech uppercase text-[#F5F5F5] hover:border-[#F5F5F5]"
        >
          {isZoomed ? "[EXIT LOUPE]" : "[INSPECT LOUPE 2X]"}
        </button>
      </div>

      {currentItem !== undefined ? (
        <div className="relative aspect-[4/3] w-full overflow-hidden border border-[#262626] bg-[#D8D8D8]">
          <img
            src={currentItem.public_url}
            alt={`Lot media ${currentItem.slot_type}`}
            className={`h-full w-full object-cover transition-transform duration-200 ${
              isZoomed ? "scale-150 cursor-zoom-out" : "scale-100 cursor-zoom-in"
            }`}
            onClick={() => {
              setIsZoomed((prev) => !prev);
            }}
          />
          <div className="absolute bottom-2 left-2 bg-[#141414]/90 px-2 py-1 text-[11px] font-mono-tech uppercase text-[#F5F5F5] border border-[#262626]">
            SLOT: {currentItem.slot_type} · #{currentItem.sort_order + 1}
          </div>
        </div>
      ) : (
        <div className="flex aspect-[4/3] w-full items-center justify-center border border-[#262626] bg-[#141414] text-xs font-mono-tech uppercase text-[#525252]">
          NO ARCHIVAL MEDIA IN SELECTED SLOT
        </div>
      )}

      <div className="grid grid-cols-4 sm:grid-cols-8 gap-2">
        {filteredMedia.map((item, idx) => {
          const isSelected = idx === activeIndex;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => {
                setActiveIndex(idx);
              }}
              className={`rounded-none border p-0.5 text-left ${
                isSelected ? "border-[#F5F5F5]" : "border-[#262626] opacity-70"
              }`}
            >
              <ReticleFrame
                size="sm"
                bracketColor={isSelected ? "#F5F5F5" : "transparent"}
                className="w-full"
              >
                <div className="aspect-square w-full overflow-hidden bg-[#262626]">
                  <img
                    src={item.public_url}
                    alt={item.slot_type}
                    className="h-full w-full object-cover"
                  />
                </div>
              </ReticleFrame>
            </button>
          );
        })}
      </div>
    </div>
  );
};
