import json
from typing import Any


def scheduled_event_metadata(controller: Any) -> dict[str, Any]:
    """Return non-sensitive metadata for a Cloudflare scheduled invocation."""
    return {
        "event.name": "digest.schedule.triggered",
        "cron.expression": str(getattr(controller, "cron", "unknown")),
        "cron.scheduled_time_ms": getattr(controller, "scheduledTime", None),
        "pipeline.state": "scaffolded",
    }


async def handle_scheduled(controller: Any, env: Any, ctx: Any) -> None:
    """Handle the Cron Trigger until the digest orchestrator is connected."""
    del env, ctx
    print(json.dumps(scheduled_event_metadata(controller), sort_keys=True))
