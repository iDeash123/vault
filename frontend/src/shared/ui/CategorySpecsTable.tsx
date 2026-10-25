import React from "react";
import type { LotSpecs } from "../types/domain";

export interface CategorySpecsTableProps {
  specs: LotSpecs;
}

interface SpecRow {
  label: string;
  value: string;
}

function buildSpecRows(specs: LotSpecs): SpecRow[] {
  switch (specs.category) {
    case "APPAREL":
      return [
        { label: "CATEGORY", value: "APPAREL" },
        { label: "BRAND", value: specs.brand },
        { label: "SEASON / ERA", value: specs.season_era },
        { label: "TAGGED SIZE", value: specs.tagged_size },
        { label: "CONDITION GRADE", value: specs.condition_grade },
        {
          label: "MEASUREMENTS (CM)",
          value: `CHEST ${String(specs.measurements_cm.chest)}cm · SHOULDERS ${String(specs.measurements_cm.shoulders)}cm · LENGTH ${String(specs.measurements_cm.length)}cm · SLEEVE ${String(specs.measurements_cm.sleeve)}cm`,
        },
        { label: "MATERIALS", value: specs.materials.join(", ") },
      ];
    case "VINYL":
      return [
        { label: "CATEGORY", value: "VINYL" },
        { label: "ARTIST", value: specs.artist },
        { label: "ALBUM TITLE", value: specs.album_title },
        { label: "LABEL", value: specs.label },
        { label: "CATALOG NUMBER", value: specs.catalog_number },
        { label: "RELEASE YEAR", value: String(specs.release_year) },
        { label: "COUNTRY PRESSING", value: specs.country_pressing },
        { label: "MEDIA GRADE (GOLDMINE)", value: specs.media_grade },
        { label: "SLEEVE GRADE (GOLDMINE)", value: specs.sleeve_grade },
        { label: "MATRIX / RUNOUT", value: specs.matrix_runout },
        { label: "SPEED (RPM)", value: `${String(specs.rpm)} RPM` },
      ];
    case "HARDWARE":
      return [
        { label: "CATEGORY", value: "HARDWARE" },
        { label: "MANUFACTURER", value: specs.manufacturer },
        { label: "MODEL NAME", value: specs.model_name },
        { label: "PRODUCTION YEAR", value: String(specs.production_year) },
        { label: "SERIAL NUMBER", value: specs.serial_number },
        { label: "VOLTAGE", value: specs.voltage },
        { label: "FUNCTIONAL STATUS", value: specs.functional_status },
        {
          label: "INCLUDED ACCESSORIES",
          value: specs.included_accessories.join(", "),
        },
      ];
    case "ARTIFACT":
      return [
        { label: "CATEGORY", value: "ARTIFACT" },
        { label: "CREATOR / MAKER", value: specs.creator_maker },
        { label: "ORIGIN / PERIOD", value: specs.origin_period },
        { label: "PRIMARY MATERIAL", value: specs.primary_material },
        {
          label: "DIMENSIONS (MM)",
          value: `${String(specs.dimensions_mm.width)} × ${String(specs.dimensions_mm.height)} × ${String(specs.dimensions_mm.depth)} mm (${String(specs.dimensions_mm.weight_grams)} g)`,
        },
        { label: "PROVENANCE SUMMARY", value: specs.provenance_summary },
        { label: "AUTHENTICATION CODE", value: specs.authentication_code },
      ];
  }
}

export const CategorySpecsTable: React.FC<CategorySpecsTableProps> = ({
  specs,
}) => {
  const rows = buildSpecRows(specs);

  return (
    <div
      data-testid="category-specs-table"
      className="rounded-none border border-[#262626] bg-[#141414]"
    >
      <div className="border-b border-[#262626] px-4 py-2.5 text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6] flex items-center justify-between">
        <span>ARCHIVAL SPECIFICATION PASSPORT</span>
        <span className="text-[#F5F5F5]">[{specs.category}]</span>
      </div>
      <dl className="divide-y divide-[#262626]">
        {rows.map((row) => (
          <div
            key={row.label}
            className="grid grid-cols-1 sm:grid-cols-12 gap-2 px-4 py-2.5 text-xs font-mono-tech"
          >
            <dt className="sm:col-span-5 text-[#A6A6A6] uppercase">
              {row.label}
            </dt>
            <dd className="sm:col-span-7 text-[#F5F5F5] break-words">
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
};
