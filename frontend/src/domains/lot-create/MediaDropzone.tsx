import React, { useRef, useState } from "react";
import { apiClient } from "../../shared/api/client";
import type {
  LotMediaItem,
  MediaSlotType,
} from "../../shared/types/domain";
import { Badge } from "../../shared/ui/Badge";
import { ReticleFrame } from "../../shared/ui/BrandGlyphs";
import { Button } from "../../shared/ui/Button";
import { Select } from "../../shared/ui/Select";

export interface LotMediaUploadResponse {
  id: string;
  lot_id: string;
  slot_type: MediaSlotType;
  storage_key: string;
  public_url: string;
  mime_type: string;
  size_bytes: number;
  sort_order: number;
  server_time: string;
}

export interface MediaDropzoneProps {
  lotId?: string | null | undefined;
  media: ReadonlyArray<LotMediaItem>;
  onMediaUploaded?: ((item: LotMediaItem) => void) | undefined;
  onUploadFile?:
    | ((slotType: MediaSlotType, file: File) => Promise<void>)
    | undefined;
  disabled?: boolean | undefined;
  errorMessage?: string | undefined;
}

export const MANDATORY_SLOTS: ReadonlyArray<MediaSlotType> = [
  "PRIMARY",
  "TAG_STAMP",
  "DEFECT",
  "DETAIL",
];

const SLOT_DEFINITIONS: Record<
  MediaSlotType,
  { label: string; description: string }
> = {
  PRIMARY: {
    label: "PRIMARY HERO",
    description: "Full-body frontal archival showcase angle",
  },
  TAG_STAMP: {
    label: "TAG / STAMP / MATRIX",
    description: "Neck tag, inner label, serial number or runout matrix",
  },
  DEFECT: {
    label: "DEFECT / PATINA",
    description: "Documented wear, intentional distressing, or flaw",
  },
  DETAIL: {
    label: "DETAIL / HARDWARE",
    description: "Close-up of weave, zipper, knobs, or material macro",
  },
};

const SLOT_SELECT_OPTIONS = MANDATORY_SLOTS.map((slot) => ({
  value: slot,
  label: `${slot} — ${SLOT_DEFINITIONS[slot].label}`,
}));

export function getMissingSlots(
  media: ReadonlyArray<LotMediaItem>,
): MediaSlotType[] {
  const uploadedSlots = new Set(media.map((m) => m.slot_type));
  return MANDATORY_SLOTS.filter((slot) => !uploadedSlots.has(slot));
}

export function isMediaSubmissionValid(
  media: ReadonlyArray<LotMediaItem>,
): boolean {
  if (media.length < 4 || media.length > 8) {
    return false;
  }
  return getMissingSlots(media).length === 0;
}

export const MediaDropzone: React.FC<MediaDropzoneProps> = ({
  lotId,
  media,
  onMediaUploaded,
  onUploadFile,
  disabled = false,
  errorMessage,
}) => {
  const [selectedSlot, setSelectedSlot] = useState<MediaSlotType>("PRIMARY");
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [localError, setLocalError] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const missingSlots = getMissingSlots(media);
  const totalCount = media.length;
  const isSubmissionReady = isMediaSubmissionValid(media);

  const handleProcessFile = async (file: File) => {
    if (disabled || isUploading) {
      return;
    }
    setLocalError("");

    const validTypes = ["image/jpeg", "image/png", "image/webp"];
    const extension = file.name.split(".").pop()?.toLowerCase();
    const validExtensions = ["jpg", "jpeg", "png", "webp"];
    const isMimeValid = validTypes.includes(file.type.toLowerCase());
    const isExtValid =
      extension !== undefined && validExtensions.includes(extension);

    if (!isMimeValid && !isExtValid) {
      setLocalError("INVALID FILE TYPE. ONLY JPEG, PNG, AND WEBP ARE PERMITTED.");
      return;
    }

    const maxBytes = 10 * 1024 * 1024;
    if (file.size > maxBytes) {
      setLocalError("FILE EXCEEDS MAXIMUM PERMITTED SIZE OF 10MB.");
      return;
    }

    if (totalCount >= 8) {
      setLocalError("MAXIMUM MEDIA CAPACITY REACHED (8 / 8 PHOTOS).");
      return;
    }

    setIsUploading(true);
    try {
      const activeSlot = selectedSlot;
      if (onUploadFile !== undefined) {
        await onUploadFile(activeSlot, file);
      } else if (lotId !== undefined && lotId !== null) {
        const formData = new FormData();
        formData.append("slot_type", activeSlot);
        formData.append("file", file);

        const response = await apiClient.post<LotMediaUploadResponse>(
          `/lots/${lotId}/media`,
          formData,
        );

        if (onMediaUploaded !== undefined) {
          onMediaUploaded({
            id: response.id,
            slot_type: response.slot_type,
            public_url: response.public_url,
            mime_type: response.mime_type,
            sort_order: response.sort_order,
          });
        }
      } else {
        setLocalError("LOT DRAFT MUST BE CREATED BEFORE UPLOADING MEDIA.");
        return;
      }

      const nextMissing = missingSlots.find((s) => s !== activeSlot);
      if (nextMissing !== undefined) {
        setSelectedSlot(nextMissing);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "MEDIA UPLOAD FAILED";
      setLocalError(msg);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current !== null) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files !== null && files.length > 0) {
      const file = files[0];
      if (file !== undefined) {
        void handleProcessFile(file);
      }
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (disabled || isUploading) {
      return;
    }
    if (e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file !== undefined) {
        void handleProcessFile(file);
      }
    }
  };

  const displayError = errorMessage || localError;

  return (
    <div
      data-testid="media-dropzone"
      className="flex flex-col gap-6 border border-[#262626] bg-[#141414] p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#262626] pb-4">
        <div className="flex items-center gap-2">
          <ReticleFrame className="text-[#A6A6A6]" />
          <span className="text-sm font-mono-tech uppercase tracking-wider text-[#F5F5F5]">
            ARCHIVAL PHOTOGRAPHY PROTOCOL (4–8 SLOTS)
          </span>
        </div>
        <div className="flex items-center gap-2 font-mono-tech text-xs">
          <span className="text-[#A6A6A6]">COUNT:</span>
          <span className="text-[#F5F5F5] font-bold">{totalCount} / 8</span>
          {isSubmissionReady ? (
            <Badge tone="live">READY FOR CURATOR</Badge>
          ) : (
            <Badge tone="reserveUnmet">MIN 4 REQUIRED</Badge>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {MANDATORY_SLOTS.map((slot) => {
          const slotItems = media.filter((m) => m.slot_type === slot);
          const isUploaded = slotItems.length > 0;
          const def = SLOT_DEFINITIONS[slot];

          return (
            <div
              key={slot}
              data-testid={`slot-card-${slot}`}
              className={`p-3 border flex flex-col justify-between gap-2 transition-colors ${
                isUploaded
                  ? "border-[#F5F5F5] bg-[#141414]"
                  : "border-[#262626] bg-[#141414] opacity-80"
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[11px] font-mono-tech uppercase font-bold text-[#F5F5F5]">
                    {slot}
                  </span>
                  {isUploaded ? (
                    <Badge tone="live">
                      [✓] UPLOADED ({slotItems.length})
                    </Badge>
                  ) : (
                    <Badge tone="reserveUnmet">[!] REQUIRED</Badge>
                  )}
                </div>
                <div className="text-[11px] font-mono-tech text-[#A6A6A6]">
                  {def.label}
                </div>
                <div className="text-[10px] font-mono-tech text-[#525252] mt-0.5">
                  {def.description}
                </div>
              </div>

              {isUploaded && slotItems[0] !== undefined && (
                <div className="h-16 w-full border border-[#262626] overflow-hidden bg-black flex items-center justify-center mt-2">
                  <img
                    src={slotItems[0].public_url}
                    alt={`${slot} preview`}
                    className="h-full w-full object-cover"
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="flex flex-col md:flex-row items-stretch md:items-end gap-4 border-t border-[#262626] pt-4">
        <div className="w-full md:w-1/2">
          <Select
            label="SELECT TARGET SLOT FOR UPLOAD"
            value={selectedSlot}
            options={SLOT_SELECT_OPTIONS}
            disabled={disabled || isUploading}
            onChange={(val) => {
              setSelectedSlot(val as MediaSlotType);
            }}
          />
        </div>

        <div className="w-full md:w-1/2 flex items-center gap-2">
          <input
            type="file"
            ref={fileInputRef}
            aria-label="Upload lot media file"
            data-testid="media-file-input"
            accept="image/jpeg,image/png,image/webp"
            disabled={disabled || isUploading}
            onChange={handleFileChange}
            className="hidden"
          />
          <Button
            variant="secondary"
            fullWidth
            disabled={disabled || isUploading || totalCount >= 8}
            isLoading={isUploading}
            onClick={() => {
              if (fileInputRef.current !== null) {
                fileInputRef.current.click();
              }
            }}
          >
            CHOOSE FILE FOR [{selectedSlot}]
          </Button>
        </div>
      </div>

      <div
        data-testid="dropzone-drop-area"
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled && !isUploading) {
            setIsDragging(true);
          }
        }}
        onDragLeave={() => {
          setIsDragging(false);
        }}
        onDrop={handleDrop}
        onClick={() => {
          if (!disabled && !isUploading && fileInputRef.current !== null) {
            fileInputRef.current.click();
          }
        }}
        className={`border-2 border-dashed p-8 flex flex-col items-center justify-center gap-2 cursor-pointer transition-colors ${
          isDragging
            ? "border-[#F5F5F5] bg-[#262626]"
            : "border-[#262626] hover:border-[#A6A6A6] bg-[#141414]"
        } ${disabled || isUploading ? "opacity-50 cursor-not-allowed" : ""}`}
      >
        <div className="text-xs font-mono-tech uppercase tracking-wider text-[#F5F5F5]">
          DRAG & DROP PHOTOGRAPH HERE OR CLICK TO BROWSE
        </div>
        <div className="text-[11px] font-mono-tech text-[#A6A6A6]">
          TARGET SLOT: [{selectedSlot}] · MAXIMUM FILE SIZE: 10MB · ACCEPTED: JPEG, PNG, WEBP
        </div>
      </div>

      {displayError.length > 0 && (
        <div
          role="alert"
          data-testid="media-dropzone-error"
          className="p-3 border border-[#F5F5F5] bg-[#141414] text-xs font-mono-tech text-[#F5F5F5]"
        >
          [ERROR] {displayError}
        </div>
      )}

      <div
        data-testid="media-status-summary"
        className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border-t border-[#262626] pt-3 text-xs font-mono-tech"
      >
        <div>
          {missingSlots.length > 0 ? (
            <span className="text-[#A6A6A6]">
              MISSING MANDATORY SLOTS:{" "}
              <span className="text-[#F5F5F5] font-bold">
                {missingSlots.join(", ")}
              </span>
            </span>
          ) : (
            <span className="text-[#F5F5F5]">
              ALL 4 MANDATORY SLOTS SATISFIED [PRIMARY, TAG_STAMP, DEFECT, DETAIL]
            </span>
          )}
        </div>
        <div className="text-[#A6A6A6]">
          {totalCount < 4 ? (
            <span>UPLOAD {4 - totalCount} MORE PHOTOS FOR SUBMISSION</span>
          ) : (
            <span className="text-[#F5F5F5]">
              {totalCount} / 8 UPLOADED ({8 - totalCount} SLOTS REMAINING)
            </span>
          )}
        </div>
      </div>

      {media.length > 0 && (
        <div className="flex flex-col gap-2 pt-2 border-t border-[#262626]">
          <span className="text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6]">
            UPLOADED ARCHIVAL MANIFEST ({media.length})
          </span>
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-2">
            {media.map((item, index) => (
              <div
                key={item.id || index}
                data-testid={`media-item-${item.slot_type}`}
                className="border border-[#262626] bg-black p-1 flex flex-col gap-1"
              >
                <div className="h-20 w-full overflow-hidden flex items-center justify-center bg-[#141414]">
                  <img
                    src={item.public_url}
                    alt={`${item.slot_type} ${String(index + 1)}`}
                    className="h-full w-full object-cover"
                  />
                </div>
                <div className="flex items-center justify-between text-[10px] font-mono-tech px-1 text-[#A6A6A6]">
                  <span>#{String(index + 1)}</span>
                  <span className="text-[#F5F5F5]">{item.slot_type}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
