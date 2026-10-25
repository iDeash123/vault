export type UserRole = "MEMBER" | "CURATOR" | "ADMIN";

export type WalletHoldStatus =
  | "ACTIVE_HOLD"
  | "CLAIMABLE"
  | "CLAIMED"
  | "CAPTURED_TO_ESCROW";

export type LedgerEntryType =
  | "STRIPE_TOPUP"
  | "BID_LOCK"
  | "BID_OUTBID_TO_CLAIMABLE"
  | "BID_RELEASED_TO_CLAIMABLE"
  | "BID_MANUAL_CLAIM"
  | "BUY_NOW_LOCK"
  | "ESCROW_BUYER_RELEASE"
  | "ESCROW_SELLER_PAYOUT"
  | "ESCROW_REFUND_TO_BUYER";

export type LotCategory = "APPAREL" | "VINYL" | "HARDWARE" | "ARTIFACT";

export type LotStatus =
  | "DRAFT"
  | "PENDING_REVIEW"
  | "SCHEDULED"
  | "LIVE"
  | "ENDED_WON"
  | "ENDED_UNSOLD"
  | "SETTLED"
  | "CANCELLED";

export type MediaSlotType = "PRIMARY" | "TAG_STAMP" | "DEFECT" | "DETAIL";

export type EscrowOrderStatus =
  | "FUNDS_HELD"
  | "SHIPPED"
  | "COMPLETED"
  | "DISPUTED"
  | "REFUNDED";

export type ModerationDecision = "APPROVED" | "REJECTED" | "CANCELLED_LIVE";

export interface ApparelSpecs {
  category: "APPAREL";
  brand: string;
  season_era: string;
  tagged_size: string;
  condition_grade: "ARCHIVAL_MINT" | "GENTLY_WORN" | "DISTRESSED" | "ALTERED";
  measurements_cm: {
    chest: number;
    shoulders: number;
    length: number;
    sleeve: number;
  };
  materials: string[];
}

export interface VinylSpecs {
  category: "VINYL";
  artist: string;
  album_title: string;
  label: string;
  catalog_number: string;
  release_year: number;
  country_pressing: string;
  media_grade: "M" | "NM" | "VG_PLUS" | "VG" | "G_PLUS";
  sleeve_grade: "M" | "NM" | "VG_PLUS" | "VG" | "G_PLUS";
  matrix_runout: string;
  rpm: 33 | 45 | 78;
}

export interface HardwareSpecs {
  category: "HARDWARE";
  manufacturer: string;
  model_name: string;
  production_year: number;
  serial_number: string;
  voltage: "100V_JP" | "120V_US" | "220V_EU" | "MULTI_VOLTAGE" | "BATTERY_DC";
  functional_status:
    | "FULLY_SERVICED_RECAPPED"
    | "WORKING_ORIGINAL"
    | "POWERS_ON_UNTESTED"
    | "FOR_PARTS_RESTORATION";
  included_accessories: string[];
}

export interface ArtifactSpecs {
  category: "ARTIFACT";
  creator_maker: string;
  origin_period: string;
  primary_material: string;
  dimensions_mm: {
    width: number;
    height: number;
    depth: number;
    weight_grams: number;
  };
  provenance_summary: string;
  authentication_code: string;
}

export type LotSpecs =
  | ApparelSpecs
  | VinylSpecs
  | HardwareSpecs
  | ArtifactSpecs;

export interface LotMediaItem {
  id: string;
  slot_type: MediaSlotType;
  public_url: string;
  mime_type: string;
  sort_order: number;
}

export interface LotDetail {
  id: string;
  seller_id: string;
  leader_user_id: string | null;
  category: LotCategory;
  status: LotStatus;
  title: string;
  subtitle: string;
  description: string;
  specs: LotSpecs;
  start_price: string;
  reserve_price: string | null;
  buy_now_price: string | null;
  min_bid_increment: string;
  current_price: string;
  min_valid_bid: string;
  bid_count: number;
  is_buy_now_available: boolean;
  is_reserve_met: boolean;
  anti_snipe_extensions_count: number;
  starts_at: string;
  ends_at: string;
  media: LotMediaItem[];
  server_time: string;
}

export interface WalletHoldItem {
  id: string;
  lot_id: string;
  lot_title: string;
  amount: string;
  status: WalletHoldStatus;
  created_at: string;
  outbid_at: string | null;
  claimed_at: string | null;
}

export interface WalletSummary {
  available_balance: string;
  held_balance: string;
  claimable_balance: string;
  holds: WalletHoldItem[];
}

export interface LedgerEntryItem {
  id: string;
  entry_type: LedgerEntryType;
  amount: string;
  available_delta: string;
  held_delta: string;
  claimable_delta: string;
  balance_available_after: string;
  balance_held_after: string;
  balance_claimable_after: string;
  reference_lot_id: string | null;
  reference_hold_id: string | null;
  created_at: string;
}

export interface WalletSummaryResponse extends WalletSummary {
  ledger_entries: LedgerEntryItem[];
  server_time?: string;
}

export interface UserProfile {
  id: string;
  email: string;
  username: string;
  role: UserRole;
  is_active: boolean;
  avatar_url: string | null;
  bio: string | null;
  available_balance: string;
  held_balance: string;
  claimable_balance: string;
}

export interface AccessTokenResponse {
  access_token: string;
  user: UserProfile;
  server_time?: string;
}

export interface ApiErrorPayload {
  error_code: string;
  message: string;
  details: Record<string, unknown>;
  server_time: string;
}

export interface LotSnapshotEvent {
  event_type: "LOT_SNAPSHOT";
  lot_id: string;
  status: LotStatus;
  current_price: string;
  min_valid_bid: string;
  bid_count: number;
  leader_user_id: string | null;
  leader_username_masked: string | null;
  is_buy_now_available: boolean;
  is_reserve_met: boolean;
  ends_at: string;
  anti_snipe_extensions_count: number;
  server_time: string;
}

export interface BidPlacedEvent {
  event_type: "BID_PLACED";
  lot_id: string;
  bid_id: string;
  amount: string;
  min_valid_bid: string;
  bid_count: number;
  leader_user_id: string;
  leader_username_masked: string;
  is_buy_now_available: boolean;
  is_reserve_met: boolean;
  ends_at: string;
  triggered_anti_snipe: boolean;
  server_time: string;
}

export interface LotExtendedEvent {
  event_type: "LOT_EXTENDED";
  lot_id: string;
  new_ends_at: string;
  anti_snipe_extensions_count: number;
  server_time: string;
}

export interface LotSoldEvent {
  event_type: "LOT_SOLD";
  lot_id: string;
  winner_user_id: string;
  final_price: string;
  via_buy_now: boolean;
  server_time: string;
}

export interface LotEndedEvent {
  event_type: "LOT_ENDED";
  lot_id: string;
  status: LotStatus;
  winner_user_id: string | null;
  final_price: string;
  server_time: string;
}

export type LotWsEvent =
  | LotSnapshotEvent
  | BidPlacedEvent
  | LotExtendedEvent
  | LotSoldEvent
  | LotEndedEvent;

export interface AuthOkEvent {
  event_type: "AUTH_OK";
  user_id: string;
  server_time: string;
}

export interface HoldBecameClaimableEvent {
  event_type: "HOLD_BECAME_CLAIMABLE";
  hold_id: string;
  lot_id: string;
  lot_title: string;
  amount: string;
  reason: string;
  new_claimable_balance: string;
  server_time: string;
}

export interface LotWonEvent {
  event_type: "LOT_WON";
  lot_id: string;
  order_id: string;
  final_amount: string;
  server_time: string;
}

export interface OrderStatusChangedEvent {
  event_type: "ORDER_STATUS_CHANGED";
  order_id: string;
  status: EscrowOrderStatus;
  server_time: string;
}

export type UserNotificationWsEvent =
  | AuthOkEvent
  | HoldBecameClaimableEvent
  | LotWonEvent
  | OrderStatusChangedEvent;
