# cart.py
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any, Union
from pathlib import Path
import json
import asyncio
from app.services.paypal_service import capture_order_with_card, get_order_details, capture_order, extract_paypal_card_details
from app.routes.rabbitmq import publish_json, emit_event
from pydantic import BaseModel
from decimal import Decimal

router = APIRouter()

# ----------------------------
# Data directory and file setup
# -----------------------------
APP_DIR = Path(__file__).parent.parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DONATIONS_FILE = DATA_DIR / "donations.json"
_write_lock = asyncio.Lock()

# -----------------------------
# Helper functions
# -----------------------------
def load_donations() -> List[Dict]:
    if not DONATIONS_FILE.exists():
        return []
    try:
        with DONATIONS_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

async def save_donations(donations: List[Dict]):
    async with _write_lock:
        with DONATIONS_FILE.open("w", encoding="utf-8") as f:
            json.dump(donations, f, indent=2, default=str)

# -----------------------------
# View cart endpoint
# -----------------------------
@router.get("/cart/view")
async def view_cart(user_id: int = Query(..., description="Current logged-in user ID")):
    """
    Returns all 'CREATING' orders for the given user_id, including amount.
    """
    donations = load_donations()
    creating_orders = [
        {
            "id": d.get("metadata", {}).get("order_id"),
            "amount": float(d.get("amount", 0)),  # convert to float
            "currency": d.get("currency", "USD"),
        }
        for d in donations
        if d.get("user_id") == user_id and d.get("status") == "CREATING"
    ]

    if not creating_orders:
        raise HTTPException(status_code=404, detail="No items in cart")

    return creating_orders






# -----------------------------
# Delete cart item endpoint.
# -----------------------------
@router.delete("/cart/delete", response_model=Dict[str, str])
async def delete_cart_item(user_id: int = Query(...), order_id: str = Query(...)):
    """
    Deletes a specific 'CREATING' donation for the given user_id and order_id
    and emits an event to RabbitMQ.
    """
    donations = load_donations()

    for i, d in enumerate(donations):
        if d.get("user_id") == user_id and d.get("metadata", {}).get("order_id") == order_id:
            if d.get("status") != "CREATING":
                raise HTTPException(status_code=400, detail="Cannot delete completed donation")
            
            # Remove donation and save
            deleted_record = donations.pop(i)
            await save_donations(donations)

            # Emit event to RabbitMQ
            await emit_event("cart_item_deleted", {
                "user_id": user_id,
                "order_id": order_id,
                "donation_info": deleted_record
            })

            return {"message": f"Order {order_id} deleted successfully"}

    # If not found
    raise HTTPException(status_code=404, detail="Cart item not found")

    
    
    
    
    
    
    
# -----------------------------
# Batch capture endpoint
# -----------------------------
class BatchCaptureRequest(BaseModel):
    order_ids: List[str]
    card: Optional[Dict] = None  # pass card details if needed

@router.post("/orders/capture-batch")
async def capture_batch(req: BatchCaptureRequest):
    donations = load_donations()
    results = []
    errors = []

    for order_id in req.order_ids:
        try:
            # Find donation record
            donation_index = next(
                (i for i, d in enumerate(donations) if d.get("metadata", {}).get("order_id") == order_id),
                None
            )
            if donation_index is None:
                raise HTTPException(status_code=404, detail=f"Donation not found for order_id {order_id}")

            donation_record = donations[donation_index]

            # Skip already completed
            if donation_record.get("status") == "COMPLETED":
                results.append({
                    "order_id": order_id,
                    "status": "already_completed",
                    "donation_info": donation_record
                })
                continue

            # -------------------
            # Capture with card
            # -------------------
            if req.card:
                capture_response = capture_order_with_card(
                    order_id=order_id,
                    card_number=req.card["card_number"],
                    card_expiry=req.card["card_expiry"],
                    card_cvv=req.card["card_cvv"],
                    full_name=req.card.get("full_name", "Unknown"),
                    billing_country=req.card.get("billing_country", "Unknown")
                )
                capture_details = capture_response['purchase_units'][0]['payments']['captures'][0]
                card_source = capture_details.get("payment_source", {}).get("card") or {}

                paypal_fee = Decimal(capture_details.get("seller_receivable_breakdown", {}).get("paypal_fee", {}).get("value", 0))
                net_amount = Decimal(capture_details.get("seller_receivable_breakdown", {}).get("net_amount", {}).get("value", capture_details.get("amount", {}).get("value", 0)))

                card_info = {
                    "card_last4": card_source.get("last_digits") or donation_record.get("card_last4"),
                    "card_brand": card_source.get("brand") or donation_record.get("card_brand"),
                    "card_type": card_source.get("type") or donation_record.get("card_type") or "CREDIT",
                    "network": capture_details.get("network_transaction_reference", {}).get("network") or donation_record.get("network"),
                    "network_reference_id": capture_details.get("network_transaction_reference", {}).get("id") or donation_record.get("network_reference_id"),
                    "full_name": card_source.get("name") or req.card.get("full_name", "Unknown"),
                    "billing_country": req.card.get("billing_country", "Unknown"),
                    "amount": capture_details.get("amount", {}).get("value", "0"),
                    "paypal_fee": paypal_fee,
                    "net_amount": net_amount,
                    "method": "card"
                }

            # -------------------
            # Capture via PayPal
            # -------------------
            else:
                capture_response = capture_order(order_id)
                capture_details = capture_response.get('purchase_units', [])[0]['payments']['captures'][0]

                paypal_fee = Decimal(capture_details.get("seller_receivable_breakdown", {}).get("paypal_fee", {}).get("value", 0))
                net_amount = Decimal(capture_details.get("seller_receivable_breakdown", {}).get("net_amount", {}).get("value", capture_details.get("amount", {}).get("value", 0)))

                card_info = extract_paypal_card_details(capture_response)
                card_source = capture_details.get("payment_source", {}).get("card") or {}

                card_info.update({
                    "card_last4": card_source.get("last_digits") or card_info.get("card_last4") or donation_record.get("card_last4"),
                    "card_brand": card_source.get("brand") or card_info.get("card_brand") or donation_record.get("card_brand"),
                    "card_type": card_source.get("type") or card_info.get("card_type") or donation_record.get("card_type") or "CREDIT",
                    "network": capture_details.get("network_transaction_reference", {}).get("network") or card_info.get("network") or donation_record.get("network"),
                    "network_reference_id": capture_details.get("network_transaction_reference", {}).get("id") or card_info.get("network_reference_id") or donation_record.get("network_reference_id"),
                    "full_name": card_source.get("name") or card_info.get("full_name") or donation_record.get("full_name"),
                    "billing_country": donation_record.get("metadata", {}).get("billing_country", "Unknown"),
                    "amount": card_info.get("amount") or donation_record.get("amount", "0"),
                    "paypal_fee": paypal_fee,
                    "net_amount": net_amount,
                    "method": "paypal"
                })

            # -------------------
            # Update donation record
            # -------------------
            donation_record.update({
                "status": "COMPLETED",
                "amount": str(card_info["amount"]),
                "card_last4": card_info["card_last4"],
                "card_brand": card_info["card_brand"],
                "card_type": card_info["card_type"],
                "network": card_info["network"],
                "network_reference_id": card_info["network_reference_id"],
                "paypal_fee": str(card_info["paypal_fee"]),
                "net_amount": str(card_info["net_amount"]),
            })

            metadata = donation_record.get("metadata", {})
            metadata.update({
                "billing_full_name": card_info["full_name"],
                "billing_country": card_info["billing_country"],
                "method": card_info["method"],
                "type": card_info["card_type"]
            })
            donation_record["metadata"] = metadata

            donations[donation_index] = donation_record
            await save_donations(donations)

            results.append({
                "order_id": order_id,
                "status": "success",
                "capture_response": capture_response,
                "donation_info": donation_record
            })

            # Emit success event
            await emit_event("order_capture", {
                "order_id": order_id,
                "status": "success",
                "donation_info": donation_record
            })

        except Exception as e:
            errors.append({"order_id": order_id, "status": "failed", "message": str(e)})
            # Emit failure event
            await emit_event("order_capture_failed", {
                "order_id": order_id,
                "message": str(e)
            })

    return {"success": True, "results": results, "errors": errors}




