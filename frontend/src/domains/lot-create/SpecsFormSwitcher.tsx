import React from "react";
import type {
  ApparelSpecs,
  HardwareSpecs,
  LotCategory,
  LotSpecs,
  VinylSpecs,
} from "../../shared/types/domain";
import { Input } from "../../shared/ui/Input";
import { Select } from "../../shared/ui/Select";

export interface SpecsFormSwitcherProps {
  category: LotCategory;
  specs: LotSpecs;
  onChange: (specs: LotSpecs) => void;
  errors?: Record<string, string> | undefined;
}

export function createDefaultSpecs(category: LotCategory): LotSpecs {
  switch (category) {
    case "APPAREL":
      return {
        category: "APPAREL",
        brand: "",
        season_era: "",
        tagged_size: "",
        condition_grade: "ARCHIVAL_MINT",
        measurements_cm: {
          chest: 0,
          shoulders: 0,
          length: 0,
          sleeve: 0,
        },
        materials: [],
      };
    case "VINYL":
      return {
        category: "VINYL",
        artist: "",
        album_title: "",
        label: "",
        catalog_number: "",
        release_year: 2000,
        country_pressing: "",
        media_grade: "NM",
        sleeve_grade: "NM",
        matrix_runout: "",
        rpm: 33,
      };
    case "HARDWARE":
      return {
        category: "HARDWARE",
        manufacturer: "",
        model_name: "",
        production_year: 1980,
        serial_number: "",
        voltage: "120V_US",
        functional_status: "WORKING_ORIGINAL",
        included_accessories: [],
      };
    case "ARTIFACT":
      return {
        category: "ARTIFACT",
        creator_maker: "",
        origin_period: "",
        primary_material: "",
        dimensions_mm: {
          width: 0,
          height: 0,
          depth: 0,
          weight_grams: 0,
        },
        provenance_summary: "",
        authentication_code: "",
      };
  }
}

const APPAREL_CONDITION_OPTIONS = [
  { value: "ARCHIVAL_MINT", label: "ARCHIVAL MINT (UNWORN ARCHIVE)" },
  { value: "GENTLY_WORN", label: "GENTLY WORN (EXCELLENT PATINA)" },
  { value: "DISTRESSED", label: "DISTRESSED (INTENTIONAL / HEAVY PATINA)" },
  { value: "ALTERED", label: "ALTERED (CUSTOMIZED / TAILORED)" },
];

const VINYL_GRADE_OPTIONS = [
  { value: "M", label: "M (MINT / SEALED)" },
  { value: "NM", label: "NM (NEAR MINT)" },
  { value: "VG_PLUS", label: "VG+ (VERY GOOD PLUS)" },
  { value: "VG", label: "VG (VERY GOOD)" },
  { value: "G_PLUS", label: "G+ (GOOD PLUS)" },
];

const VINYL_RPM_OPTIONS = [
  { value: "33", label: "33 1/3 RPM (LP)" },
  { value: "45", label: "45 RPM (12\" / 7\" SINGLE)" },
  { value: "78", label: "78 RPM (SHELLAC ARCHIVE)" },
];

const HARDWARE_VOLTAGE_OPTIONS = [
  { value: "120V_US", label: "120V (US / NORTH AMERICA)" },
  { value: "220V_EU", label: "220V–240V (EU / UK ARCHIVE)" },
  { value: "100V_JP", label: "100V (JAPAN DOMESTIC)" },
  { value: "MULTI_VOLTAGE", label: "MULTI-VOLTAGE SWITCHABLE" },
  { value: "BATTERY_DC", label: "BATTERY / DC POWERED" },
];

const HARDWARE_STATUS_OPTIONS = [
  {
    value: "FULLY_SERVICED_RECAPPED",
    label: "FULLY SERVICED & RECAPPED (BENCH TESTED)",
  },
  {
    value: "WORKING_ORIGINAL",
    label: "WORKING ORIGINAL (UNMODIFIED COMPONENT)",
  },
  {
    value: "POWERS_ON_UNTESTED",
    label: "POWERS ON / UNTESTED (COLLECTOR AS-IS)",
  },
  {
    value: "FOR_PARTS_RESTORATION",
    label: "FOR PARTS / RESTORATION PROJECT",
  },
];

function parseCommaSeparated(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function stringArraysEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) {
    return false;
  }
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) {
      return false;
    }
  }
  return true;
}

export const SpecsFormSwitcher: React.FC<SpecsFormSwitcherProps> = ({
  category,
  specs,
  onChange,
  errors = {},
}) => {
  const [materialsInput, setMaterialsInput] = React.useState<string>(() => {
    if (specs.category === "APPAREL") {
      return specs.materials.join(", ");
    }
    return "";
  });

  const [accessoriesInput, setAccessoriesInput] = React.useState<string>(() => {
    if (specs.category === "HARDWARE") {
      return specs.included_accessories.join(", ");
    }
    return "";
  });

  const prevCategoryRef = React.useRef(category);

  React.useEffect(() => {
    if (prevCategoryRef.current !== category) {
      prevCategoryRef.current = category;
      if (specs.category === "APPAREL") {
        setMaterialsInput(specs.materials.join(", "));
      } else if (specs.category === "HARDWARE") {
        setAccessoriesInput(specs.included_accessories.join(", "));
      }
      return;
    }
    if (specs.category === "APPAREL") {
      const parsed = parseCommaSeparated(materialsInput);
      if (!stringArraysEqual(parsed, specs.materials)) {
        setMaterialsInput(specs.materials.join(", "));
      }
    } else if (specs.category === "HARDWARE") {
      const parsed = parseCommaSeparated(accessoriesInput);
      if (!stringArraysEqual(parsed, specs.included_accessories)) {
        setAccessoriesInput(specs.included_accessories.join(", "));
      }
    }
  }, [category, specs, materialsInput, accessoriesInput]);

  if (specs.category !== category) {
    return (
      <div className="p-4 border border-[#262626] bg-[#141414] text-xs font-mono-tech text-[#A6A6A6]">
        CATEGORY MISMATCH. INITIALIZING SPECS FOR [{category}]...
      </div>
    );
  }

  if (specs.category === "APPAREL") {
    const apparel = specs;
    return (
      <div
        data-testid="specs-form-apparel"
        className="flex flex-col gap-4 border border-[#262626] bg-[#141414] p-4"
      >
        <div className="border-b border-[#262626] pb-2 text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6] flex justify-between">
          <span>APPAREL SPECIFICATION SCHEMA</span>
          <span className="text-[#F5F5F5]">[ARCHIVAL FASHION]</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Input
            label="BRAND / DESIGNER"
            value={apparel.brand}
            error={errors["specs.brand"]}
            onChange={(e) => {
              onChange({ ...apparel, brand: e.target.value });
            }}
            placeholder="e.g. Raf Simons, Maison Margiela"
          />
          <Input
            label="SEASON / ERA"
            value={apparel.season_era}
            error={errors["specs.season_era"]}
            onChange={(e) => {
              onChange({ ...apparel, season_era: e.target.value });
            }}
            placeholder="e.g. AW01 Riot! Riot! Riot!"
          />
          <Input
            label="TAGGED SIZE"
            value={apparel.tagged_size}
            error={errors["specs.tagged_size"]}
            onChange={(e) => {
              onChange({ ...apparel, tagged_size: e.target.value });
            }}
            placeholder="e.g. 48, M, US 10"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Select
            label="CONDITION GRADE"
            value={apparel.condition_grade}
            options={APPAREL_CONDITION_OPTIONS}
            error={errors["specs.condition_grade"]}
            onChange={(val) => {
              onChange({
                ...apparel,
                condition_grade: val as ApparelSpecs["condition_grade"],
              });
            }}
          />
          <Input
            label="MATERIALS (COMMA-SEPARATED)"
            value={materialsInput}
            error={errors["specs.materials"]}
            onChange={(e) => {
              const raw = e.target.value;
              setMaterialsInput(raw);
              const list = parseCommaSeparated(raw);
              onChange({ ...apparel, materials: list });
            }}
            placeholder="e.g. 100% Heavy Cotton, Riri Zippers"
          />
        </div>

        <div className="flex flex-col gap-2 pt-2 border-t border-[#262626]">
          <span className="text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6]">
            MEASUREMENTS (CM)
          </span>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Input
              label="CHEST"
              type="number"
              mono
              value={apparel.measurements_cm.chest || ""}
              error={errors["specs.measurements_cm.chest"]}
              onChange={(e) => {
                const chest = parseFloat(e.target.value) || 0;
                onChange({
                  ...apparel,
                  measurements_cm: { ...apparel.measurements_cm, chest },
                });
              }}
              placeholder="0.0"
            />
            <Input
              label="SHOULDERS"
              type="number"
              mono
              value={apparel.measurements_cm.shoulders || ""}
              error={errors["specs.measurements_cm.shoulders"]}
              onChange={(e) => {
                const shoulders = parseFloat(e.target.value) || 0;
                onChange({
                  ...apparel,
                  measurements_cm: { ...apparel.measurements_cm, shoulders },
                });
              }}
              placeholder="0.0"
            />
            <Input
              label="LENGTH"
              type="number"
              mono
              value={apparel.measurements_cm.length || ""}
              error={errors["specs.measurements_cm.length"]}
              onChange={(e) => {
                const length = parseFloat(e.target.value) || 0;
                onChange({
                  ...apparel,
                  measurements_cm: { ...apparel.measurements_cm, length },
                });
              }}
              placeholder="0.0"
            />
            <Input
              label="SLEEVE"
              type="number"
              mono
              value={apparel.measurements_cm.sleeve || ""}
              error={errors["specs.measurements_cm.sleeve"]}
              onChange={(e) => {
                const sleeve = parseFloat(e.target.value) || 0;
                onChange({
                  ...apparel,
                  measurements_cm: { ...apparel.measurements_cm, sleeve },
                });
              }}
              placeholder="0.0"
            />
          </div>
        </div>
      </div>
    );
  }

  if (specs.category === "VINYL") {
    const vinyl = specs;
    return (
      <div
        data-testid="specs-form-vinyl"
        className="flex flex-col gap-4 border border-[#262626] bg-[#141414] p-4"
      >
        <div className="border-b border-[#262626] pb-2 text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6] flex justify-between">
          <span>VINYL SPECIFICATION SCHEMA</span>
          <span className="text-[#F5F5F5]">[ARCHIVAL PRESSING]</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="ARTIST"
            value={vinyl.artist}
            error={errors["specs.artist"]}
            onChange={(e) => {
              onChange({ ...vinyl, artist: e.target.value });
            }}
            placeholder="e.g. Aphex Twin, Joy Division"
          />
          <Input
            label="ALBUM TITLE"
            value={vinyl.album_title}
            error={errors["specs.album_title"]}
            onChange={(e) => {
              onChange({ ...vinyl, album_title: e.target.value });
            }}
            placeholder="e.g. Drukqs, Unknown Pleasures"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Input
            label="RECORD LABEL"
            value={vinyl.label}
            error={errors["specs.label"]}
            onChange={(e) => {
              onChange({ ...vinyl, label: e.target.value });
            }}
            placeholder="e.g. Warp Records, Factory"
          />
          <Input
            label="CATALOG NUMBER"
            value={vinyl.catalog_number}
            error={errors["specs.catalog_number"]}
            onChange={(e) => {
              onChange({ ...vinyl, catalog_number: e.target.value });
            }}
            placeholder="e.g. WARPLP92, FACT 10"
          />
          <Input
            label="RELEASE YEAR"
            type="number"
            mono
            value={vinyl.release_year || ""}
            error={errors["specs.release_year"]}
            onChange={(e) => {
              const release_year = parseInt(e.target.value, 10) || 0;
              onChange({ ...vinyl, release_year });
            }}
            placeholder="2001"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="COUNTRY PRESSING"
            value={vinyl.country_pressing}
            error={errors["specs.country_pressing"]}
            onChange={(e) => {
              onChange({ ...vinyl, country_pressing: e.target.value });
            }}
            placeholder="e.g. UK First Press, Japan Obi Press"
          />
          <Input
            label="MATRIX / RUNOUT ETCHING"
            value={vinyl.matrix_runout}
            error={errors["specs.matrix_runout"]}
            onChange={(e) => {
              onChange({ ...vinyl, matrix_runout: e.target.value });
            }}
            placeholder="e.g. WARPLP 92 A-01-01"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Select
            label="MEDIA GRADE (GOLDMINE)"
            value={vinyl.media_grade}
            options={VINYL_GRADE_OPTIONS}
            error={errors["specs.media_grade"]}
            onChange={(val) => {
              onChange({
                ...vinyl,
                media_grade: val as VinylSpecs["media_grade"],
              });
            }}
          />
          <Select
            label="SLEEVE GRADE (GOLDMINE)"
            value={vinyl.sleeve_grade}
            options={VINYL_GRADE_OPTIONS}
            error={errors["specs.sleeve_grade"]}
            onChange={(val) => {
              onChange({
                ...vinyl,
                sleeve_grade: val as VinylSpecs["sleeve_grade"],
              });
            }}
          />
          <Select
            label="SPEED (RPM)"
            value={String(vinyl.rpm)}
            options={VINYL_RPM_OPTIONS}
            error={errors["specs.rpm"]}
            onChange={(val) => {
              onChange({
                ...vinyl,
                rpm: parseInt(val, 10) as VinylSpecs["rpm"],
              });
            }}
          />
        </div>
      </div>
    );
  }

  if (specs.category === "HARDWARE") {
    const hardware = specs;
    return (
      <div
        data-testid="specs-form-hardware"
        className="flex flex-col gap-4 border border-[#262626] bg-[#141414] p-4"
      >
        <div className="border-b border-[#262626] pb-2 text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6] flex justify-between">
          <span>HARDWARE SPECIFICATION SCHEMA</span>
          <span className="text-[#F5F5F5]">[VINTAGE INSTRUMENT & HI-FI]</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="MANUFACTURER"
            value={hardware.manufacturer}
            error={errors["specs.manufacturer"]}
            onChange={(e) => {
              onChange({ ...hardware, manufacturer: e.target.value });
            }}
            placeholder="e.g. Roland, Leica, Sony, Braun"
          />
          <Input
            label="MODEL NAME"
            value={hardware.model_name}
            error={errors["specs.model_name"]}
            onChange={(e) => {
              onChange({ ...hardware, model_name: e.target.value });
            }}
            placeholder="e.g. TR-808, M6 TTL, TPS-L2"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="PRODUCTION YEAR"
            type="number"
            mono
            value={hardware.production_year || ""}
            error={errors["specs.production_year"]}
            onChange={(e) => {
              const production_year = parseInt(e.target.value, 10) || 0;
              onChange({ ...hardware, production_year });
            }}
            placeholder="1981"
          />
          <Input
            label="SERIAL NUMBER"
            value={hardware.serial_number}
            error={errors["specs.serial_number"]}
            onChange={(e) => {
              onChange({ ...hardware, serial_number: e.target.value });
            }}
            placeholder="e.g. SN-808-49102"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Select
            label="OPERATING VOLTAGE"
            value={hardware.voltage}
            options={HARDWARE_VOLTAGE_OPTIONS}
            error={errors["specs.voltage"]}
            onChange={(val) => {
              onChange({
                ...hardware,
                voltage: val as HardwareSpecs["voltage"],
              });
            }}
          />
          <Select
            label="FUNCTIONAL STATUS"
            value={hardware.functional_status}
            options={HARDWARE_STATUS_OPTIONS}
            error={errors["specs.functional_status"]}
            onChange={(val) => {
              onChange({
                ...hardware,
                functional_status: val as HardwareSpecs["functional_status"],
              });
            }}
          />
        </div>

        <Input
          label="INCLUDED ACCESSORIES (COMMA-SEPARATED)"
          value={accessoriesInput}
          error={errors["specs.included_accessories"]}
          onChange={(e) => {
            const raw = e.target.value;
            setAccessoriesInput(raw);
            const list = parseCommaSeparated(raw);
            onChange({ ...hardware, included_accessories: list });
          }}
          placeholder="e.g. Original Box, Flight Case, Power Supply"
        />
      </div>
    );
  }

  const artifact = specs;
  return (
    <div
      data-testid="specs-form-artifact"
      className="flex flex-col gap-4 border border-[#262626] bg-[#141414] p-4"
    >
      <div className="border-b border-[#262626] pb-2 text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6] flex justify-between">
        <span>ARTIFACT SPECIFICATION SCHEMA</span>
        <span className="text-[#F5F5F5]">[DESIGN OBJECT & ARCHIVE]</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Input
          label="CREATOR / MAKER"
          value={artifact.creator_maker}
          error={errors["specs.creator_maker"]}
          onChange={(e) => {
            onChange({ ...artifact, creator_maker: e.target.value });
          }}
          placeholder="e.g. Dieter Rams, Ettore Sottsass"
        />
        <Input
          label="ORIGIN / PERIOD"
          value={artifact.origin_period}
          error={errors["specs.origin_period"]}
          onChange={(e) => {
            onChange({ ...artifact, origin_period: e.target.value });
          }}
          placeholder="e.g. 1968 West Germany, Late 1970s Milan"
        />
        <Input
          label="PRIMARY MATERIAL"
          value={artifact.primary_material}
          error={errors["specs.primary_material"]}
          onChange={(e) => {
            onChange({ ...artifact, primary_material: e.target.value });
          }}
          placeholder="e.g. Anodized Aluminum, Bakelite"
        />
      </div>

      <div className="flex flex-col gap-2 pt-2 border-t border-[#262626]">
        <span className="text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6]">
          DIMENSIONS (MM) & WEIGHT (G)
        </span>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Input
            label="WIDTH (MM)"
            type="number"
            mono
            value={artifact.dimensions_mm.width || ""}
            error={errors["specs.dimensions_mm.width"]}
            onChange={(e) => {
              const width = parseFloat(e.target.value) || 0;
              onChange({
                ...artifact,
                dimensions_mm: { ...artifact.dimensions_mm, width },
              });
            }}
            placeholder="0"
          />
          <Input
            label="HEIGHT (MM)"
            type="number"
            mono
            value={artifact.dimensions_mm.height || ""}
            error={errors["specs.dimensions_mm.height"]}
            onChange={(e) => {
              const height = parseFloat(e.target.value) || 0;
              onChange({
                ...artifact,
                dimensions_mm: { ...artifact.dimensions_mm, height },
              });
            }}
            placeholder="0"
          />
          <Input
            label="DEPTH (MM)"
            type="number"
            mono
            value={artifact.dimensions_mm.depth || ""}
            error={errors["specs.dimensions_mm.depth"]}
            onChange={(e) => {
              const depth = parseFloat(e.target.value) || 0;
              onChange({
                ...artifact,
                dimensions_mm: { ...artifact.dimensions_mm, depth },
              });
            }}
            placeholder="0"
          />
          <Input
            label="WEIGHT (GRAMS)"
            type="number"
            mono
            value={artifact.dimensions_mm.weight_grams || ""}
            error={errors["specs.dimensions_mm.weight_grams"]}
            onChange={(e) => {
              const weight_grams = parseFloat(e.target.value) || 0;
              onChange({
                ...artifact,
                dimensions_mm: { ...artifact.dimensions_mm, weight_grams },
              });
            }}
            placeholder="0"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input
          label="PROVENANCE SUMMARY"
          value={artifact.provenance_summary}
          error={errors["specs.provenance_summary"]}
          onChange={(e) => {
            onChange({ ...artifact, provenance_summary: e.target.value });
          }}
          placeholder="Documented chain of ownership and certificates"
        />
        <Input
          label="AUTHENTICATION CODE"
          value={artifact.authentication_code}
          error={errors["specs.authentication_code"]}
          onChange={(e) => {
            onChange({ ...artifact, authentication_code: e.target.value });
          }}
          placeholder="e.g. COA-BRAUN-1987-04"
        />
      </div>
    </div>
  );
};
