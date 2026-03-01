from fastapi import APIRouter, HTTPException, Request
from app.services import hooks
from app.routes.rabbitmq import emit_event

router = APIRouter()

@router.post("/webhook")
async def paypal_webhook(request: Request):
    payload = {}
    try:
        payload = await request.json()
        await hooks.log_request(request)

        event_type = payload.get("event_type", "unknown")
        resource = payload.get("resource", {})
        debug_info = hooks.extract_debug_info(resource)

        hooks.logger.info(
            f"[WEBHOOK] Event: {event_type} | Resource ID: {resource.get('id', 'N/A')} | "
            f"Debug info: {debug_info}"
        )

        await emit_event("paypal.webhook.received", {
            "paypal_event_type": event_type,
            "resource_id": resource.get("id"),
            "resource_status": resource.get("status"),
            "debug_info": debug_info,
            "payload": payload,
        })

        return {"success": True, "event_type": event_type, "debug_info": debug_info}
    except Exception as e:
        await hooks.log_error(request, e)
        try:
            await emit_event("paypal.webhook.failed", {
                "error": str(e),
                "payload": payload,
            })
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(e))
