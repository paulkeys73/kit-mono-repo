from messaging.rabbitmq import emit_event

from datetime import datetime

async def emit_stats_snapshot():
    await emit_event(
        "donation.stats.snapshot",
        {
            "requested_at": datetime.utcnow().isoformat(),
            "source": "donation_consumer",
        }
    )
