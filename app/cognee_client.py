"""Cliente minimo de la API de Cognee (solo lecturas, salvo la busqueda que no modifica datos)."""
from __future__ import annotations

import threading
import time

import httpx

from . import config

_lock = threading.Lock()
_token: dict = {"value": None, "at": 0.0}


class CogneeUnavailable(RuntimeError):
    pass


def _api_key_headers() -> dict | None:
    return {"X-Api-Key": config.COGNEE_API_KEY} if config.COGNEE_API_KEY else None


def _login() -> str:
    r = httpx.post(f"{config.COGNEE_API_URL}/api/v1/auth/login",
                   data={"username": config.COGNEE_USER_EMAIL, "password": config.COGNEE_USER_PASSWORD}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def _headers(force: bool = False) -> dict:
    key = _api_key_headers()
    if key:
        return key
    with _lock:
        if force or not _token["value"] or time.time() - _token["at"] > 1800:
            _token["value"], _token["at"] = _login(), time.time()
        return {"Authorization": f"Bearer {_token['value']}"}


def request(method: str, path: str, json=None, timeout: float = 60):
    try:
        for attempt in (0, 1):
            r = httpx.request(method, config.COGNEE_API_URL + path, headers=_headers(force=attempt == 1),
                              json=json, timeout=timeout)
            if r.status_code == 401 and attempt == 0:
                continue
            r.raise_for_status()
            return r.json() if r.content else None
    except (httpx.HTTPError, KeyError) as exc:
        raise CogneeUnavailable(str(exc)[:200]) from exc


def get(path: str, **kw):
    return request("GET", path, **kw)


def post(path: str, json=None, **kw):
    return request("POST", path, json=json, **kw)


def health() -> dict:
    try:
        r = httpx.get(f"{config.COGNEE_API_URL}/health", timeout=4)
        return {"ok": r.status_code == 200, **(r.json() if r.content else {})}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc)[:120]}
