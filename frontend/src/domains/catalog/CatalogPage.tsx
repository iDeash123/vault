import React, { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "../../shared/api/client";
import type {
  LotCategory,
  LotDetail,
  LotStatus,
} from "../../shared/types/domain";
import { ReticleFrame, SlashedZeroGlyph } from "../../shared/ui/BrandGlyphs";
import { Button } from "../../shared/ui/Button";
import { Input } from "../../shared/ui/Input";
import { SkeletonBox } from "../../shared/ui/SkeletonBox";
import { FilterSidebar } from "./FilterSidebar";
import { LotCard } from "./LotCard";

export interface LotCatalogResponse {
  items: LotDetail[];
  total: number;
  limit: number;
  offset: number;
  server_time: string;
}

export const CatalogPage: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [activeSearch, setActiveSearch] = useState<string>("");
  const [category, setCategory] = useState<LotCategory | "ALL">("ALL");
  const [status, setStatus] = useState<LotStatus | "ALL">("ALL");
  const [minPrice, setMinPrice] = useState<string>("");
  const [maxPrice, setMaxPrice] = useState<string>("");
  const [sortBy, setSortBy] = useState<string>("ending_soon");

  const [lots, setLots] = useState<LotDetail[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string>("");

  const requestIdRef = useRef<number>(0);

  const fetchCatalog = useCallback(async () => {
    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);
    setErrorMessage("");
    try {
      const params: Record<string, string | number | boolean | undefined | null> = {
        sort: sortBy,
        limit: 50,
        offset: 0,
      };

      if (activeSearch.trim().length > 0) {
        params["q"] = activeSearch.trim();
      }
      if (category !== "ALL") {
        params["category"] = category;
      }
      if (status !== "ALL") {
        params["status"] = status;
      }

      let parsedMin: number | null = null;
      if (minPrice.trim().length > 0) {
        const val = parseFloat(minPrice.replace(/^\$/, "").trim());
        if (!isNaN(val)) {
          if (val < 0) {
            if (requestIdRef.current === currentRequestId) {
              setErrorMessage("MIN PRICE MUST BE POSITIVE.");
              setIsLoading(false);
            }
            return;
          }
          parsedMin = val;
          params["min_price"] = val.toFixed(2);
        }
      }

      let parsedMax: number | null = null;
      if (maxPrice.trim().length > 0) {
        const val = parseFloat(maxPrice.replace(/^\$/, "").trim());
        if (!isNaN(val)) {
          if (val < 0) {
            if (requestIdRef.current === currentRequestId) {
              setErrorMessage("MAX PRICE MUST BE POSITIVE.");
              setIsLoading(false);
            }
            return;
          }
          parsedMax = val;
          params["max_price"] = val.toFixed(2);
        }
      }

      if (parsedMin !== null && parsedMax !== null && parsedMin > parsedMax) {
        if (requestIdRef.current === currentRequestId) {
          setErrorMessage("MIN PRICE CANNOT EXCEED MAX PRICE.");
          setIsLoading(false);
        }
        return;
      }

      const response = await apiClient.get<LotCatalogResponse>("/lots", params);
      if (requestIdRef.current === currentRequestId) {
        setLots(response.items);
        setTotal(response.total);
      }
    } catch (err) {
      if (requestIdRef.current === currentRequestId) {
        const msg = err instanceof Error ? err.message : "FAILED TO LOAD CATALOG";
        setErrorMessage(msg);
      }
    } finally {
      if (requestIdRef.current === currentRequestId) {
        setIsLoading(false);
      }
    }
  }, [activeSearch, category, status, minPrice, maxPrice, sortBy]);

  useEffect(() => {
    void fetchCatalog();
  }, [fetchCatalog]);

  const handleSearchSubmit = (e?: React.SyntheticEvent) => {
    if (e !== undefined) {
      e.preventDefault();
    }
    setActiveSearch(searchQuery);
  };

  const handleResetFilters = () => {
    setSearchQuery("");
    setActiveSearch("");
    setCategory("ALL");
    setStatus("ALL");
    setMinPrice("");
    setMaxPrice("");
    setSortBy("ending_soon");
  };

  return (
    <div
      data-testid="catalog-page"
      className="mx-auto max-w-[1400px] flex flex-col gap-8 py-8 px-4 sm:px-6"
    >
      <div className="flex flex-col gap-4 border-b border-[#262626] pb-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono-tech text-[#A6A6A6]">
              <span>01 / ARCHIVAL CATALOG</span>
              <span>·</span>
              <span>LIVE BIDDING CONDUIT</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold font-mono-tech uppercase tracking-wider text-[#F5F5F5] mt-1 flex items-center gap-3">
              <SlashedZeroGlyph className="w-8 h-10" />
              <span>OBSOLETE LIVE ARCHIVE</span>
            </h1>
          </div>

          <div className="flex items-center gap-3 font-mono-tech text-xs">
            <span className="text-[#A6A6A6]">INDEX STATUS:</span>
            <span className="text-[#F5F5F5] font-bold">
              {String(total)} SPECIMENS CATALOGUED
            </span>
          </div>
        </div>

        <form
          onSubmit={handleSearchSubmit}
          className="flex flex-col sm:flex-row items-stretch gap-2 pt-2"
        >
          <div className="flex-1">
            <Input
              label="FULL-TEXT CATALOG SEARCH"
              mono
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
              }}
              placeholder="SEARCH BY DESIGNER, ARTIST, MODEL, MATRIX, ERA..."
            />
          </div>
          <div className="flex items-end gap-2">
            <Button
              type="submit"
              variant="primary"
              className="h-[38px]"
            >
              SEARCH ARCHIVE
            </Button>
            {activeSearch.length > 0 && (
              <Button
                type="button"
                variant="ghost"
                className="h-[38px]"
                onClick={() => {
                  setSearchQuery("");
                  setActiveSearch("");
                }}
              >
                CLEAR [{activeSearch}]
              </Button>
            )}
          </div>
        </form>
      </div>

      {errorMessage.length > 0 && (
        <div
          role="alert"
          data-testid="catalog-error-alert"
          className="p-4 border border-[#F5F5F5] bg-[#141414] text-xs font-mono-tech text-[#F5F5F5] flex items-center justify-between"
        >
          <span>[SYSTEM NOTICE] {errorMessage}</span>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              void fetchCatalog();
            }}
          >
            RETRY
          </Button>
        </div>
      )}

      <div className="flex flex-col md:flex-row items-start gap-8">
        <FilterSidebar
          selectedCategory={category}
          onCategoryChange={setCategory}
          selectedStatus={status}
          onStatusChange={setStatus}
          minPrice={minPrice}
          maxPrice={maxPrice}
          onMinPriceChange={setMinPrice}
          onMaxPriceChange={setMaxPrice}
          sortBy={sortBy}
          onSortByChange={setSortBy}
          onResetFilters={handleResetFilters}
        />

        <main className="flex-1 w-full flex flex-col gap-6">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#262626] pb-3 text-xs font-mono-tech">
            <div className="text-[#A6A6A6]">
              SHOWING <span className="text-[#F5F5F5] font-bold">{String(lots.length)}</span> OF{" "}
              <span className="text-[#F5F5F5] font-bold">{String(total)}</span> SPECIMENS
            </div>
            {category !== "ALL" && (
              <span className="text-[#A6A6A6]">
                CATEGORY: <span className="text-[#F5F5F5]">[{category}]</span>
              </span>
            )}
          </div>

          {isLoading ? (
            <div
              data-testid="catalog-loading-grid"
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6"
            >
              {[1, 2, 3, 4, 5, 6].map((idx) => (
                <div
                  key={idx}
                  className="flex flex-col gap-3 border border-[#262626] bg-[#141414] p-4"
                >
                  <SkeletonBox className="h-60 w-full" />
                  <SkeletonBox className="h-6 w-3/4" />
                  <SkeletonBox className="h-4 w-1/2" />
                  <div className="grid grid-cols-2 gap-2 mt-2">
                    <SkeletonBox className="h-10 w-full" />
                    <SkeletonBox className="h-10 w-full" />
                  </div>
                </div>
              ))}
            </div>
          ) : lots.length === 0 ? (
            <div
              data-testid="catalog-empty-state"
              className="border border-[#262626] bg-[#141414] p-12 flex flex-col items-center justify-center gap-4 text-center"
            >
              <ReticleFrame size="lg" className="text-[#525252]" />
              <div className="flex flex-col gap-1 font-mono-tech">
                <span className="text-sm font-bold uppercase text-[#F5F5F5]">
                  NO SPECIMENS MATCH SPECIFIED ARCHIVAL QUERY
                </span>
                <span className="text-xs text-[#A6A6A6]">
                  Adjust category boundaries, price range, or reset query parameters.
                </span>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleResetFilters}
              >
                RESET ALL FILTERS
              </Button>
            </div>
          ) : (
            <div
              data-testid="catalog-lots-grid"
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6"
            >
              {lots.map((lot) => (
                <LotCard key={lot.id} lot={lot} />
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
};
