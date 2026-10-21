import asyncio
import json
from datetime import UTC, datetime
from typing import Any

try:
    from workers import DurableObject
except ImportError:  # pragma: no cover - local pytest fallback

    class DurableObject:  # type: ignore[no-redef]
        def __init__(self, ctx: Any, env: Any) -> None:
            self.ctx = ctx
            self.env = env


from worker_orchestrator import run_digest
from worker_runtime import env_value

DIGEST_COORDINATOR_NAME = "daily-digest"


def _invocation_time(scheduled_time_ms: int | float | None) -> datetime:
    if scheduled_time_ms is None:
        return datetime.now(UTC)
    return datetime.fromtimestamp(float(scheduled_time_ms) / 1000, UTC)


async def dispatch_digest(
    env: Any,
    *,
    scheduled_time_ms: int | float | None = None,
    dry_run: bool = True,
    target_user_id: int | None = None,
    target_date: str | None = None,
) -> dict[str, Any]:
    """Dispatch a digest run across the Durable Object execution boundary."""
    namespace = env_value(env, "DIGEST_COORDINATOR")
    if namespace is None:
        raise RuntimeError("missing_digest_coordinator_binding")

    stub = namespace.getByName(DIGEST_COORDINATOR_NAME)
    if target_date is not None:
        return await stub.run(scheduled_time_ms, dry_run, target_user_id, target_date)
    return await stub.run(scheduled_time_ms, dry_run, target_user_id)


class DigestCoordinator(DurableObject):
    """Serialize digest runs and give parsing a Durable Object CPU budget."""

    async def run(
        self,
        scheduled_time_ms: int | float | None = None,
        dry_run: bool = True,
        target_user_id: int | None = None,
        target_date: str | None = None,
    ) -> dict[str, Any]:
        invocation_time = _invocation_time(scheduled_time_ms)
        if not hasattr(self, "_run_lock"):
            self._run_lock = asyncio.Lock()
        async with self._run_lock:
            return await self._run_serialized(
                invocation_time, dry_run, target_user_id, target_date
            )

    async def _run_serialized(
        self,
        invocation_time: datetime,
        dry_run: bool,
        target_user_id: int | None,
        target_date: str | None,
    ) -> dict[str, Any]:
        print(
            json.dumps(
                {
                    "event.name": "digest.coordinator.started",
                    "pipeline.state": "dry_run" if dry_run else "live",
                    "targeted": target_user_id is not None,
                },
                sort_keys=True,
            )
        )
        runner = env_value(self.env, "RUN_DIGEST", run_digest)
        extra = {"target_date": target_date} if target_date is not None else {}
        return await runner(
            self.env,
            now=invocation_time,
            dry_run=bool(dry_run),
            target_user_id=target_user_id,
            **extra,
        )
