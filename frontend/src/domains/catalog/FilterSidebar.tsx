import React from "react";
import type { LotCategory, LotStatus } from "../../shared/types/domain";
import { ReticleFrame } from "../../shared/ui/BrandGlyphs";
import { Button } from "../../shared/ui/Button";
import { Input } from "../../shared/ui/Input";
import { Select } from "../../shared/ui/Select";

export interface FilterSidebarProps {
  selectedCategory: LotCategory | "ALL";
  onCategoryChange: (category: LotCategory | "ALL") => void;
  selectedStatus: LotStatus | "ALL";
  onStatusChange: (status: LotStatus | "ALL") => void;
  minPrice: string;
  maxPrice: string;
  onMinPriceChange: (val: string) => void;
  onMaxPriceChange: (val: string) => void;
  sortBy: string;
  onSortByChange: (sort: string) => void;
  onResetFilters: () => void;
}

const CATEGORIES: ReadonlyArray<{ value: LotCategory | "ALL"; label: string }> = [
  { value: "ALL", label: "00 / ALL ARCHIVE SPECIMENS" },
  { value: "APPAREL", label: "01 / ARCHIVAL APPAREL" },
  { value: "VINYL", label: "02 / RARE VINYL PRESSINGS" },
  { value: "HARDWARE", label: "03 / VINTAGE HARDWARE" },
  { value: "ARTIFACT", label: "04 / INDUSTRIAL ARTIFACTS" },
];

const STATUS_OPTIONS = [
  { value: "ALL", label: "ALL STATUSES" },
  { value: "LIVE", label: "ACTIVE LIVE BIDDING" },
  { value: "SCHEDULED", label: "SCHEDULED UPCOMING" },
  { value: "ENDED_WON", label: "ENDED & WON" },
  { value: "ENDED_UNSOLD", label: "ENDED UNSOLD" },
];

const SORT_OPTIONS = [
  { value: "ending_soon", label: "TIME: ENDING SOONEST" },
  { value: "hot_bids", label: "ACTIVITY: MOST BIDS" },
  { value: "newest", label: "CHRONO: NEWEST LISTED" },
  { value: "price_asc", label: "PRICE: LOWEST FIRST" },
  { value: "price_desc", label: "PRICE: HIGHEST FIRST" },
];

export const FilterSidebar: React.FC<FilterSidebarProps> = ({
  selectedCategory,
  onCategoryChange,
  selectedStatus,
  onStatusChange,
  minPrice,
  maxPrice,
  onMinPriceChange,
  onMaxPriceChange,
  sortBy,
  onSortByChange,
  onResetFilters,
}) => {
  return (
    <aside
      data-testid="filter-sidebar"
      className="flex flex-col gap-6 border border-[#262626] bg-[#141414] p-5 w-full md:w-72 shrink-0"
    >
      <div className="flex items-center justify-between border-b border-[#262626] pb-3">
        <span className="text-xs font-mono-tech uppercase tracking-wider text-[#F5F5F5] font-bold">
          CATALOG FILTERS
        </span>
        <button
          type="button"
          data-testid="reset-filters-button"
          onClick={onResetFilters}
          className="text-[11px] font-mono-tech uppercase text-[#A6A6A6] hover:text-[#F5F5F5] underline"
        >
          RESET ALL
        </button>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6]">
          ARCHIVAL CATEGORY
        </span>
        <div className="flex flex-col gap-1">
          {CATEGORIES.map((cat) => {
            const isSelected = selectedCategory === cat.value;
            return (
              <button
                key={cat.value}
                type="button"
                data-testid={`category-filter-${cat.value.toLowerCase()}`}
                onClick={() => {
                  onCategoryChange(cat.value);
                }}
                className={`text-left rounded-none border px-3 py-2 text-xs font-mono-tech uppercase tracking-wider transition-colors flex items-center justify-between ${
                  isSelected
                    ? "border-[#F5F5F5] bg-[#F5F5F5] text-[#141414] font-semibold"
                    : "border-[#262626] bg-[#141414] text-[#A6A6A6] hover:border-[#F5F5F5] hover:text-[#F5F5F5]"
                }`}
              >
                <span>{cat.label}</span>
                {isSelected && <ReticleFrame size="sm" />}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <Select
          label="AUCTION STATUS"
          value={selectedStatus}
          options={STATUS_OPTIONS}
          onChange={(val) => {
            onStatusChange(val as LotStatus | "ALL");
          }}
        />
      </div>

      <div className="flex flex-col gap-2">
        <Select
          label="ORDER BY"
          value={sortBy}
          options={SORT_OPTIONS}
          onChange={onSortByChange}
        />
      </div>

      <div className="flex flex-col gap-2 border-t border-[#262626] pt-4">
        <span className="text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6]">
          PRICE RANGE (USD)
        </span>
        <div className="grid grid-cols-2 gap-2">
          <Input
            label="MIN"
            type="number"
            mono
            prefixText="$"
            value={minPrice}
            onChange={(e) => {
              onMinPriceChange(e.target.value);
            }}
            placeholder="0"
          />
          <Input
            label="MAX"
            type="number"
            mono
            prefixText="$"
            value={maxPrice}
            onChange={(e) => {
              onMaxPriceChange(e.target.value);
            }}
            placeholder="Max"
          />
        </div>
      </div>

      <div className="pt-2">
        <Button
          variant="secondary"
          size="sm"
          fullWidth
          onClick={onResetFilters}
        >
          CLEAR ALL FILTERS
        </Button>
      </div>
    </aside>
  );
};
