import json
from datetime import UTC, datetime
from typing import Any

from worker_orchestrator import run_digest
from worker_runtime import env_value


def scheduled_event_metadata(controller: Any, dry_run: bool = True) -> dict[str, Any]:
    """Return non-sensitive metadata for a Cloudflare scheduled invocation."""
    return {
        "event.name": "digest.schedule.triggered",
        "cron.expression": str(getattr(controller, "cron", "unknown")),
        "cron.scheduled_time_ms": getattr(controller, "scheduledTime", None),
        "pipeline.state": "dry_run" if dry_run else "live",
    }


async def handle_scheduled(controller: Any, env: Any, ctx: Any) -> None:
    """Run the digest pipeline; production delivery is opt-in and fail-closed."""
    del ctx
    enabled = str(env_value(env, "DIGEST_DELIVERY_ENABLED", "false")).lower() in {
        "1",
        "true",
        "yes",
    }
    dry_run = not enabled
    print(json.dumps(scheduled_event_metadata(controller, dry_run), sort_keys=True))
    scheduled_time = getattr(controller, "scheduledTime", None)
    now = (
        datetime.fromtimestamp(float(scheduled_time) / 1000, UTC)
        if scheduled_time is not None
        else datetime.now(UTC)
    )
    runner = env_value(env, "RUN_DIGEST", run_digest)
    await runner(env, now=now, dry_run=dry_run)
