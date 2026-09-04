from typing import Any

try:
    from workers import Response, WorkerEntrypoint
except ImportError:  # pragma: no cover - local pytest fallback
    Response = None

    class WorkerEntrypoint:  # type: ignore[no-redef]
        pass


from worker_app import handle_request
from worker_http import AppResponse
from worker_schedule import handle_scheduled


def _to_worker_response(response: AppResponse) -> Any:
    if Response is None:  # pragma: no cover - exercised only in Cloudflare
        return response
    return Response(response.body, status=response.status, headers=response.headers)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return _to_worker_response(await handle_request(request, self.env))

    async def scheduled(self, controller, env, ctx):
        await handle_scheduled(controller, env, ctx)
