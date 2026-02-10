from fastapi import APIRouter, HTTPException, Request
from app.services import hooks

router = APIRouter()

@router.post("/webhook")
async def paypal_webhook(request: Request):
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

        return {"success": True, "event_type": event_type, "debug_info": debug_info}
    except Exception as e:
        await hooks.log_error(request, e)
        raise HTTPException(status_code=400, detail=str(e))
