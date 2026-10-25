import type { UserRole } from "../../shared/types/domain";

export interface NavItem {
  indexCode: string;
  label: string;
  subLabel: string;
  path: string;
  requiresAuth?: boolean | undefined;
  allowedRoles?: ReadonlyArray<UserRole> | undefined;
}

export const NAV_ITEMS: ReadonlyArray<NavItem> = [
  {
    indexCode: "01",
    label: "CATALOG",
    subLabel: "LIVE ARCHIVE",
    path: "/catalog",
  },
  {
    indexCode: "02",
    label: "CONSIGN",
    subLabel: "CREATE LOT",
    path: "/lots/new",
    requiresAuth: true,
  },
  {
    indexCode: "03",
    label: "WATCHLIST",
    subLabel: "SAVED LOTS",
    path: "/watchlist",
    requiresAuth: true,
  },
  {
    indexCode: "04",
    label: "WALLET",
    subLabel: "LEDGER & CLAIMS",
    path: "/wallet",
    requiresAuth: true,
  },
  {
    indexCode: "05",
    label: "ESCROW",
    subLabel: "SETTLEMENTS",
    path: "/orders",
    requiresAuth: true,
  },
  {
    indexCode: "06",
    label: "CURATOR",
    subLabel: "MODERATION",
    path: "/moderation",
    requiresAuth: true,
    allowedRoles: ["CURATOR", "ADMIN"],
  },
  {
    indexCode: "07",
    label: "SPECIMENS",
    subLabel: "KITCHEN SINK",
    path: "/kitchen-sink",
  },
];
