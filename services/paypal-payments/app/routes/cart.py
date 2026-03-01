from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from decimal import Decimal
from app.services.paypal_service import capture_order_with_card, get_order_details, capture_order, extract_paypal_card_details
from app.routes.rabbitmq import emit_event
from app.routes.payments import fetch_donation_by_order, update_donation, db, trigger_stats_refresh

router = APIRouter()


# -----------------------------
# DB Helper: Fetch all CREATING orders for a user
# -----------------------------
def fetch_creating_orders(user_id: int) -> List[Dict[str, Any]]:
    conn = db()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM payments WHERE user_id = %s AND status = 'CREATING'",
                (user_id,)
            )
            return cur.fetchall()
    finally:
        conn.close()


# -----------------------------
# View cart endpoint
# -----------------------------
@router.get("/cart/view")
async def view_cart(user_id: int = Query(..., description="Current logged-in user ID")):
    creating_orders = fetch_creating_orders(user_id)
    if not creating_orders:
        raise HTTPException(status_code=404, detail="No items in cart")

    return [
        {
            "id": d["paypal_order_id"],
            "amount": float(d["amount"]),
            "currency": d["currency"]
        }
        for d in creating_orders
    ]


# -----------------------------
# Delete cart item endpoint
# -----------------------------
@router.delete("/cart/delete", response_model=Dict[str, str])
async def delete_cart_item(user_id: int = Query(...), order_id: str = Query(...)):
    donation = fetch_donation_by_order(order_id)
    if donation["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    if donation["status"] != "CREATING":
        raise HTTPException(status_code=400, detail="Cannot delete completed donation")

    # Mark as deleted (or remove)
    update_donation(order_id, {"status": "DELETED"})
    
    # Emit event
    await emit_event("cart_item_deleted", {
        "user_id": user_id,
        "order_id": order_id,
        "donation_info": donation
    })

    return {"message": f"Order {order_id} deleted successfully"}


# -----------------------------
# Batch capture endpoint
# -----------------------------
class BatchCaptureRequest(BaseModel):
    order_ids: List[str]
    card: Optional[Dict[str, Any]] = None  # Card details if needed


@router.post("/orders/capture-batch")
async def capture_batch(req: BatchCaptureRequest):
    results = []
    errors = []

    for order_id in req.order_ids:
        try:
            donation_record = fetch_donation_by_order(order_id)

            if donation_record["status"] == "COMPLETED":
                results.append({
                    "order_id": order_id,
                    "status": "already_completed",
                    "donation_info": donation_record
                })
                continue

            # Capture
            if req.card:
                capture_response = capture_order_with_card(
                    order_id=order_id,
                    card_number=req.card["card_number"],
                    card_expiry=req.card["card_expiry"],
                    card_cvv=req.card["card_cvv"],
                    full_name=req.card.get("full_name", donation_record["full_name"]),
                    billing_country=req.card.get("billing_country", donation_record.get("billing_country", "Unknown"))
                )
                card_info = extract_paypal_card_details(capture_response)
                card_info["method"] = "card"
                card_info["billing_country"] = req.card.get("billing_country", "Unknown")
            else:
                capture_response = capture_order(order_id)
                card_info = extract_paypal_card_details(capture_response)
                card_info["method"] = "paypal"
                card_info["billing_country"] = donation_record.get("billing_country", "Unknown")

            # Compute amounts
            capture_details = capture_response["purchase_units"][0]["payments"]["captures"][0]
            card_info["amount"] = Decimal(capture_details["amount"]["value"])
            card_info["paypal_fee"] = Decimal(capture_details["seller_receivable_breakdown"]["paypal_fee"]["value"])
            card_info["net_amount"] = Decimal(capture_details["seller_receivable_breakdown"]["net_amount"]["value"])

            # Update donation in DB
            metadata = donation_record.get("metadata", {})
            metadata.update({
                "billing_full_name": card_info.get("full_name", donation_record["full_name"]),
                "billing_country": card_info["billing_country"],
                "method": card_info["method"],
                "type": card_info.get("card_type", "UNKNOWN")
            })

            update_fields = {
                "status": "COMPLETED",
                "amount": card_info["amount"],
                "paypal_fee": card_info["paypal_fee"],
                "net_amount": card_info["net_amount"],
                "card_last4": card_info.get("card_last4", donation_record.get("card_last4")),
                "card_brand": card_info.get("card_brand", donation_record.get("card_brand")),
                "card_type": card_info.get("card_type", donation_record.get("card_type")),
                "network": card_info.get("network", donation_record.get("network")),
                "network_reference_id": card_info.get("network_reference_id", donation_record.get("network_reference_id")),
                "metadata": metadata
            }

            updated_donation = update_donation(order_id, update_fields)

            results.append({
                "order_id": order_id,
                "status": "success",
                "capture_response": capture_response,
                "donation_info": updated_donation
            })

            await emit_event("order_capture", {
                "order_id": order_id,
                "status": "success",
                "donation_info": updated_donation
            })
            await trigger_stats_refresh("order_capture.batch.success", order_id)

        except Exception as e:
            errors.append({"order_id": order_id, "status": "failed", "message": str(e)})
            await emit_event("order_capture_failed", {
                "order_id": order_id,
                "message": str(e)
            })

    return {"success": True, "results": results, "errors": errors}
