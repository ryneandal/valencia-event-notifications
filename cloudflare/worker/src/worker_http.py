import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppResponse:
    body: str
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    async def json(self) -> Any:
        return json.loads(self.body)


def normalize_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    normalized = {"content-type": "application/json; charset=utf-8"}
    for key, value in (headers or {}).items():
        normalized[key.lower()] = value
    return normalized


def json_response(
    data: dict[str, Any],
    status: int = 200,
    extra_headers: dict[str, str] | None = None,
) -> AppResponse:
    return AppResponse(
        body=json.dumps(data),
        status=status,
        headers=normalize_headers(extra_headers),
    )
