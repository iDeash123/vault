import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiClientError, apiClient } from "../../shared/api/client";
import { useAuthStore } from "../../shared/store/authStore";
import type { EscrowOrderStatus } from "../../shared/types/domain";
import { Badge, type BadgeTone } from "../../shared/ui/Badge";
import { ReticleFrame, UnborderedWord } from "../../shared/ui/BrandGlyphs";
import { Button } from "../../shared/ui/Button";
import { Card } from "../../shared/ui/Card";
import { Input } from "../../shared/ui/Input";
import { Modal } from "../../shared/ui/Modal";
import { SkeletonBox } from "../../shared/ui/SkeletonBox";

export interface EscrowOrderDto {
  id: string;
  lot_id: string;
  lot_title: string;
  buyer_id: string;
  seller_id: string;
  wallet_hold_id: string;
  final_amount: string;
  platform_fee_amount: string;
  seller_payout_amount: string;
  status: EscrowOrderStatus;
  tracking_number: string | null;
  shipping_carrier: string | null;
  shipped_at: string | null;
  completed_at: string | null;
  dispute_reason: string | null;
  created_at: string;
  updated_at: string;
  server_time: string;
}

export interface EscrowOrderListDto {
  items: EscrowOrderDto[];
  total: number;
  server_time: string;
}

type RoleFilter = "ALL" | "BUYER" | "SELLER";
type StatusFilter = "ALL" | EscrowOrderStatus;

function resolveStatusTone(status: EscrowOrderStatus): BadgeTone {
  if (status === "FUNDS_HELD") {
    return "claimable";
  }
  if (status === "SHIPPED") {
    return "live";
  }
  if (status === "COMPLETED") {
    return "reserveMet";
  }
  if (status === "DISPUTED") {
    return "endingSoon";
  }
  return "neutral";
}

function resolveStatusLabel(status: EscrowOrderStatus): string {
  if (status === "FUNDS_HELD") {
    return "ESCROW LOCKED";
  }
  if (status === "SHIPPED") {
    return "IN TRANSIT";
  }
  if (status === "COMPLETED") {
    return "COMPLETED & RELEASED";
  }
  if (status === "DISPUTED") {
    return "UNDER ARBITRATION";
  }
  return "REFUNDED";
}

export const OrdersPage: React.FC = () => {
  const user = useAuthStore((state) => state.user);

  const [orders, setOrders] = useState<EscrowOrderDto[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [successMessage, setSuccessMessage] = useState<string>("");

  const [roleFilter, setRoleFilter] = useState<RoleFilter>("ALL");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");

  const [activeShipOrderId, setActiveShipOrderId] = useState<string | null>(null);
  const [carrierInput, setCarrierInput] = useState<string>("");
  const [trackingInput, setTrackingInput] = useState<string>("");
  const [isShipping, setIsShipping] = useState<boolean>(false);
  const [shipModalError, setShipModalError] = useState<string>("");

  const [activeDisputeOrderId, setActiveDisputeOrderId] = useState<string | null>(null);
  const [disputeReasonInput, setDisputeReasonInput] = useState<string>("");
  const [isDisputing, setIsDisputing] = useState<boolean>(false);
  const [disputeModalError, setDisputeModalError] = useState<string>("");

  const [isConfirmingId, setIsConfirmingId] = useState<string | null>(null);

  const loadOrders = useCallback(async () => {
    if (!user) {
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setErrorMessage("");
    try {
      const response = await apiClient.get<EscrowOrderListDto>("/orders");
      setOrders(response.items);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setErrorMessage(err.message || "Failed to load escrow orders");
      } else {
        setErrorMessage("Unexpected error loading escrow orders");
      }
    } finally {
      setIsLoading(false);
    }
  }, [user]);

  useEffect(() => {
    void loadOrders();
  }, [loadOrders]);

  const handleOpenShipModal = (orderId: string) => {
    setActiveShipOrderId(orderId);
    setCarrierInput("");
    setTrackingInput("");
    setShipModalError("");
  };

  const handleCloseShipModal = () => {
    setActiveShipOrderId(null);
    setCarrierInput("");
    setTrackingInput("");
    setShipModalError("");
  };

  const handleSubmitShipment = async (e?: React.SyntheticEvent) => {
    if (e) {
      e.preventDefault();
    }
    if (!activeShipOrderId) {
      return;
    }
    const carrier = carrierInput.trim();
    const tracking = trackingInput.trim();

    if (!carrier) {
      setShipModalError("Shipping carrier is required");
      return;
    }
    if (!tracking) {
      setShipModalError("Tracking number is required");
      return;
    }

    setIsShipping(true);
    setShipModalError("");
    setErrorMessage("");
    try {
      const updated = await apiClient.post<EscrowOrderDto>(
        `/orders/${activeShipOrderId}/ship`,
        {
          shipping_carrier: carrier,
          tracking_number: tracking,
        },
      );
      setOrders((prev) =>
        prev.map((o) => (o.id === updated.id ? { ...o, ...updated } : o)),
      );
      setSuccessMessage(`Order marked as shipped via ${carrier} (${tracking})`);
      handleCloseShipModal();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setShipModalError(err.message || "Failed to submit shipping info");
      } else {
        setShipModalError("Unexpected error submitting shipment");
      }
    } finally {
      setIsShipping(false);
    }
  };

  const handleConfirmReceipt = async (orderId: string) => {
    setIsConfirmingId(orderId);
    setErrorMessage("");
    try {
      const updated = await apiClient.post<EscrowOrderDto>(
        `/orders/${orderId}/confirm-receipt`,
      );
      const latestUser = useAuthStore.getState().user;
      if (latestUser !== null && latestUser.id === updated.buyer_id) {
        const nextHeld = Math.max(
          0,
          Number(latestUser.held_balance) - Number(updated.final_amount),
        ).toFixed(2);
        useAuthStore.getState().updateBalances({ held_balance: nextHeld });
      }
      setOrders((prev) =>
        prev.map((o) => (o.id === updated.id ? { ...o, ...updated } : o)),
      );
      setSuccessMessage("Receipt confirmed. Escrow funds released to seller.");
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setErrorMessage(err.message || "Failed to confirm receipt");
      } else {
        setErrorMessage("Unexpected error confirming receipt");
      }
    } finally {
      setIsConfirmingId(null);
    }
  };

  const handleOpenDisputeModal = (orderId: string) => {
    setActiveDisputeOrderId(orderId);
    setDisputeReasonInput("");
    setDisputeModalError("");
  };

  const handleCloseDisputeModal = () => {
    setActiveDisputeOrderId(null);
    setDisputeReasonInput("");
    setDisputeModalError("");
  };

  const handleSubmitDispute = async (e?: React.SyntheticEvent) => {
    if (e) {
      e.preventDefault();
    }
    if (!activeDisputeOrderId) {
      return;
    }
    const reason = disputeReasonInput.trim();
    if (reason.length < 5) {
      setDisputeModalError("Dispute reason must be at least 5 characters");
      return;
    }

    setIsDisputing(true);
    setDisputeModalError("");
    setErrorMessage("");
    try {
      const updated = await apiClient.post<EscrowOrderDto>(
        `/orders/${activeDisputeOrderId}/dispute`,
        {
          dispute_reason: reason,
        },
      );
      setOrders((prev) =>
        prev.map((o) => (o.id === updated.id ? { ...o, ...updated } : o)),
      );
      setSuccessMessage("Dispute submitted for curator arbitration.");
      handleCloseDisputeModal();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setDisputeModalError(err.message || "Failed to submit dispute");
      } else {
        setDisputeModalError("Unexpected error submitting dispute");
      }
    } finally {
      setIsDisputing(false);
    }
  };

  if (!user) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-12">
        <ReticleFrame size="lg" className="border border-[#262626] bg-[#141414] p-8 text-center">
          <h1 className="font-display text-2xl font-bold uppercase tracking-tight text-[#F5F5F5]">
            AUTHENTICATION REQUIRED
          </h1>
          <p className="mt-2 text-sm text-[#A6A6A6]">
            Sign in to view your escrow settlements, dispatch shipments, and release funds.
          </p>
          <div className="mt-6 flex justify-center gap-4">
            <Link to="/login">
              <Button variant="primary">LOG IN</Button>
            </Link>
            <Link to="/register">
              <Button variant="secondary">REGISTER</Button>
            </Link>
          </div>
        </ReticleFrame>
      </div>
    );
  }

  const filteredOrders = orders.filter((o) => {
    if (roleFilter === "BUYER" && o.buyer_id !== user.id) {
      return false;
    }
    if (roleFilter === "SELLER" && o.seller_id !== user.id) {
      return false;
    }
    if (statusFilter !== "ALL" && o.status !== statusFilter) {
      return false;
    }
    return true;
  });

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-8 flex flex-col gap-2 border-b border-[#262626] pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <UnborderedWord word="OBSOLETE" />
            <span className="font-mono-tech text-xs uppercase tracking-widest text-[#A6A6A6]">
              [ SECTION 05 // ESCROW SETTLEMENTS ]
            </span>
          </div>
          <h1 className="mt-1 font-display text-3xl font-black uppercase tracking-tight text-[#F5F5F5]">
            ESCROW & SETTLEMENTS
          </h1>
          <p className="mt-1 text-sm text-[#A6A6A6]">
            Dual-custody funds lock, seller dispatch tracking, and buyer release verification.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            void loadOrders();
          }}
        >
          REFRESH
        </Button>
      </div>

      {errorMessage && (
        <div
          role="alert"
          className="mb-6 border border-[#F5F5F5] bg-[#141414] p-4 font-mono-tech text-xs uppercase text-[#F5F5F5]"
        >
          [ERROR] {errorMessage}
        </div>
      )}

      {successMessage && (
        <div
          role="status"
          className="mb-6 border border-[#F5F5F5] bg-[#141414] p-4 font-mono-tech text-xs uppercase text-[#F5F5F5]"
        >
          [SUCCESS] {successMessage}
        </div>
      )}

      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border border-[#262626] bg-[#141414] p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono-tech text-xs uppercase text-[#A6A6A6]">ROLE:</span>
          {(["ALL", "BUYER", "SELLER"] as const).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => {
                setRoleFilter(r);
              }}
              className={`px-3 py-1 text-xs font-mono-tech uppercase transition-colors ${
                roleFilter === r
                  ? "bg-[#F5F5F5] text-[#141414] font-bold"
                  : "border border-[#262626] text-[#A6A6A6] hover:border-[#F5F5F5] hover:text-[#F5F5F5]"
              }`}
            >
              {r === "ALL" ? "ALL ROLES" : r === "BUYER" ? "PURCHASES" : "SALES"}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono-tech text-xs uppercase text-[#A6A6A6]">STATUS:</span>
          {(["ALL", "FUNDS_HELD", "SHIPPED", "COMPLETED", "DISPUTED"] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                setStatusFilter(s);
              }}
              className={`px-2.5 py-1 text-xs font-mono-tech uppercase transition-colors ${
                statusFilter === s
                  ? "bg-[#F5F5F5] text-[#141414] font-bold"
                  : "border border-[#262626] text-[#A6A6A6] hover:border-[#F5F5F5] hover:text-[#F5F5F5]"
              }`}
            >
              {s === "ALL" ? "ALL" : s.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-4">
          <SkeletonBox className="h-36 w-full" />
          <SkeletonBox className="h-36 w-full" />
          <SkeletonBox className="h-36 w-full" />
        </div>
      ) : filteredOrders.length === 0 ? (
        <ReticleFrame size="md" className="border border-[#262626] bg-[#141414] p-12 text-center">
          <p className="font-mono-tech text-sm uppercase text-[#A6A6A6]">
            NO ESCROW ORDERS FOUND MATCHING CURRENT FILTERS
          </p>
          <div className="mt-4">
            <Link to="/catalog">
              <Button variant="secondary" size="sm">
                EXPLORE CATALOG
              </Button>
            </Link>
          </div>
        </ReticleFrame>
      ) : (
        <div className="flex flex-col gap-4">
          {filteredOrders.map((order) => {
            const isBuyer = order.buyer_id === user.id;
            const isSeller = order.seller_id === user.id;

            return (
              <Card
                key={order.id}
                className="flex flex-col gap-4 border border-[#262626] bg-[#141414] p-6 transition-colors hover:border-[#525252]"
              >
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <Badge tone={isBuyer ? "category" : "reserveMet"}>
                        {isBuyer ? "BUYER" : "SELLER"}
                      </Badge>
                      <Badge tone={resolveStatusTone(order.status)}>
                        {resolveStatusLabel(order.status)}
                      </Badge>
                      <span className="font-mono-tech text-xs text-[#525252]">
                        ID: {order.id.slice(0, 8)}...
                      </span>
                    </div>
                    <Link
                      to={`/lots/${order.lot_id}`}
                      className="mt-2 block font-display text-xl font-bold uppercase tracking-tight text-[#F5F5F5] hover:underline"
                    >
                      {order.lot_title}
                    </Link>
                  </div>

                  <div className="text-right">
                    <span className="block font-mono-tech text-xs uppercase text-[#A6A6A6]">
                      FINAL ESCROW AMOUNT
                    </span>
                    <span className="font-mono text-2xl font-bold text-[#F5F5F5] tabular-nums">
                      ${order.final_amount}
                    </span>
                    {isSeller && (
                      <div className="mt-1 font-mono-tech text-xs text-[#A6A6A6]">
                        <span>Fee: -${order.platform_fee_amount}</span>
                        <span className="ml-2 font-bold text-[#F5F5F5]">
                          Net Payout: ${order.seller_payout_amount}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-4 border-t border-[#262626] pt-4 sm:grid-cols-2 lg:grid-cols-4 font-mono-tech text-xs text-[#A6A6A6]">
                  <div>
                    <span className="block text-[#525252] uppercase">ORDER CREATED</span>
                    <span className="text-[#D8D8D8]">
                      {new Date(order.created_at).toLocaleString()}
                    </span>
                  </div>

                  <div>
                    <span className="block text-[#525252] uppercase">SHIPPING CARRIER</span>
                    <span className="text-[#D8D8D8]">
                      {order.shipping_carrier || "NOT YET DISPATCHED"}
                    </span>
                  </div>

                  <div>
                    <span className="block text-[#525252] uppercase">TRACKING NUMBER</span>
                    <span className="text-[#D8D8D8]">
                      {order.tracking_number || "—"}
                    </span>
                  </div>

                  <div>
                    <span className="block text-[#525252] uppercase">SETTLEMENT DATE</span>
                    <span className="text-[#D8D8D8]">
                      {order.completed_at
                        ? new Date(order.completed_at).toLocaleString()
                        : order.shipped_at
                        ? `Shipped ${new Date(order.shipped_at).toLocaleDateString()}`
                        : "AWAITING DISPATCH"}
                    </span>
                  </div>
                </div>

                {order.dispute_reason && (
                  <div className="border border-[#F5F5F5] bg-[#141414] p-3 font-mono-tech text-xs text-[#F5F5F5]">
                    <span className="font-bold uppercase">[DISPUTE REASON]:</span> {order.dispute_reason}
                  </div>
                )}

                <div className="flex flex-wrap items-center justify-end gap-3 border-t border-[#262626] pt-4">
                  {isSeller && order.status === "FUNDS_HELD" && (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => {
                        handleOpenShipModal(order.id);
                      }}
                      data-testid={`ship-btn-${order.id}`}
                    >
                      DISPATCH SHIPMENT
                    </Button>
                  )}

                  {isBuyer && order.status === "SHIPPED" && (
                    <Button
                      variant="primary"
                      size="sm"
                      isLoading={isConfirmingId === order.id}
                      onClick={() => {
                        void handleConfirmReceipt(order.id);
                      }}
                      data-testid={`confirm-receipt-btn-${order.id}`}
                    >
                      Confirm Receipt & Release Escrow
                    </Button>
                  )}

                  {isBuyer &&
                    (order.status === "FUNDS_HELD" || order.status === "SHIPPED") && (
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => {
                          handleOpenDisputeModal(order.id);
                        }}
                        data-testid={`dispute-btn-${order.id}`}
                      >
                        OPEN DISPUTE
                      </Button>
                    )}
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <Modal
        isOpen={activeShipOrderId !== null}
        onClose={handleCloseShipModal}
        title="DISPATCH SHIPMENT"
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={handleCloseShipModal}>
              CANCEL
            </Button>
            <Button
              variant="primary"
              size="sm"
              isLoading={isShipping}
              onClick={() => {
                void handleSubmitShipment();
              }}
            >
              CONFIRM DISPATCH
            </Button>
          </>
        }
      >
        <form
          onSubmit={(e) => {
            void handleSubmitShipment(e);
          }}
          className="flex flex-col gap-4"
        >
          <p className="text-xs text-[#A6A6A6]">
            Provide courier carrier and tracking number. The buyer will be notified in real-time.
          </p>

          <Input
            label="SHIPPING CARRIER"
            aria-label="Shipping Carrier"
            placeholder="e.g. DHL Express, FedEx, UPS"
            value={carrierInput}
            onChange={(e) => {
              setCarrierInput(e.target.value);
            }}
            data-testid="carrier-input"
            required
          />

          <Input
            label="TRACKING NUMBER"
            aria-label="Tracking Number"
            placeholder="e.g. DHL-9876543210"
            value={trackingInput}
            onChange={(e) => {
              setTrackingInput(e.target.value);
            }}
            data-testid="tracking-input"
            mono
            required
          />

          {shipModalError && (
            <div
              role="alert"
              className="border border-[#F5F5F5] bg-[#141414] p-2 text-xs font-mono-tech text-[#F5F5F5]"
            >
              [ERROR] {shipModalError}
            </div>
          )}
        </form>
      </Modal>

      <Modal
        isOpen={activeDisputeOrderId !== null}
        onClose={handleCloseDisputeModal}
        title="OPEN ESCROW DISPUTE"
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={handleCloseDisputeModal}>
              CANCEL
            </Button>
            <Button
              variant="danger"
              size="sm"
              isLoading={isDisputing}
              onClick={() => {
                void handleSubmitDispute();
              }}
            >
              SUBMIT DISPUTE
            </Button>
          </>
        }
      >
        <form
          onSubmit={(e) => {
            void handleSubmitDispute(e);
          }}
          className="flex flex-col gap-4"
        >
          <p className="text-xs text-[#A6A6A6]">
            State the exact reason for the dispute. A platform curator will review shipment tracking and lot specifications.
          </p>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="dispute-reason-input"
              className="text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6]"
            >
              DISPUTE REASON
            </label>
            <textarea
              id="dispute-reason-input"
              rows={4}
              aria-label="Dispute Reason"
              data-testid="dispute-reason-input"
              className="w-full border border-[#262626] bg-[#141414] p-3 text-sm text-[#F5F5F5] placeholder-[#525252] focus:border-[#F5F5F5] focus:outline-none"
              placeholder="Describe condition discrepancy, damage, or non-delivery..."
              value={disputeReasonInput}
              onChange={(e) => {
                setDisputeReasonInput(e.target.value);
              }}
              required
            />
          </div>

          {disputeModalError && (
            <div
              role="alert"
              className="border border-[#F5F5F5] bg-[#141414] p-2 text-xs font-mono-tech text-[#F5F5F5]"
            >
              [ERROR] {disputeModalError}
            </div>
          )}
        </form>
      </Modal>
    </div>
  );
};
