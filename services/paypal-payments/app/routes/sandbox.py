from fastapi import APIRouter, Request, HTTPException
from app.models.requests import CreateOrderRequest
from app.services.paypal_service import create_order
from app.config import settings
import app.services.hooks as hooks
import app.services.email_service as email_service
from app.routes.rabbitmq import emit_event

router = APIRouter()
captures = {}  # you may share with orders.py if needed

@router.post("/sandbox-create-and-capture")
async def sandbox_create_and_capture(req: CreateOrderRequest, request: Request):
    if settings.PAYPAL_MODE != "sandbox":
        raise HTTPException(status_code=403, detail="Sandbox-only endpoint")
    try:
        order = create_order(req.amount, req.currency)
        order_id = order["id"]
        order["status"] = "APPROVED"
        order["links"].append({
            "href": f"https://www.sandbox.paypal.com/checkoutnow?token={order_id}",
            "rel": "approve",
            "method": "GET"
        })
        capture = {
            "id": f"CAPTURE-{order_id}",
            "status": "COMPLETED",
            "amount": {"currency_code": req.currency, "value": req.amount},
            "links": [{"href": f"/capture-order/{order_id}", "rel": "self", "method": "POST"}]
        }
        captures[order_id] = capture
        await hooks.log_request(request)
        await hooks.log_response(request, 200, {"order": order, "capture": capture})

        try:
            email_service.send_payment_success_email(
                to_email=settings.SMTP_USERNAME,
                customer_name="Sandbox User",
                amount=req.amount,
                currency=req.currency,
                order_id=order_id
            )
        except Exception as e:
            hooks.logger.error(f"[EMAIL FAILED] {e}")

        await emit_event("paypal.sandbox.captured", {
            "order_id": order_id,
            "user_id": req.user_id,
            "amount": req.amount,
            "currency": req.currency,
            "status": "COMPLETED",
            "mode": "sandbox",
        })

        return {"success": True, "order_id": order_id, "order": order, "capture": capture}
    except Exception as e:
        await hooks.log_error(request, e)
        try:
            await emit_event("paypal.sandbox.capture.failed", {
                "user_id": req.user_id,
                "amount": req.amount,
                "currency": req.currency,
                "error": str(e),
            })
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(e))
