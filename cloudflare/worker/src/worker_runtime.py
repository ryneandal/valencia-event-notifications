from typing import Any


def to_python(value: Any) -> Any:
    if value is None:
        return None

    to_py = getattr(value, "to_py", None)
    if callable(to_py):
        try:
            return to_py()
        except TypeError:
            return to_py(depth=-1)

    return value


def record_to_dict(record: Any) -> dict[str, Any] | None:
    record = to_python(record)
    if record is None:
        return None
    if isinstance(record, dict):
        return record

    result: dict[str, Any] = {}
    for key in ("id", "email", "preferences_blob", "is_active", "session_id"):
        if hasattr(record, key):
            result[key] = getattr(record, key)
    return result or None


def env_value(env: Any, name: str, default: Any = None) -> Any:
    if hasattr(env, name):
        return getattr(env, name)
    if isinstance(env, dict):
        return env.get(name, default)
    return default


def header_get(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if callable(getter):
        return getter(name)
    if isinstance(headers, dict):
        return headers.get(name)
    return None


def request_path(url: str) -> str:
    path = url
    if "://" in path:
        path = path.split("://", 1)[1]
        path = "/" + path.split("/", 1)[1] if "/" in path else "/"
    return path.split("?", 1)[0].split("#", 1)[0]


async def request_json(request: Any) -> dict[str, Any]:
    payload = await request.json()
    payload = to_python(payload)
    return payload if isinstance(payload, dict) else {}
