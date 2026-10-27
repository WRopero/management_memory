"""Estado de contenedores y llamadas a la API de Cognee (logs de acceso), via un proxy de Docker de SOLO LECTURA.

El proxy (wollomatic/socket-proxy) solo deja pasar GET de /containers/json, /containers/<id>/json|logs|stats.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import re
import struct
import time
from urllib.parse import quote

import httpx

from . import config

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_LINE = re.compile(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)\S* (\d+\.\d+\.\d+\.\d+):\d+ - "([A-Z]+) (\S+) HTTP/[\d.]+" (\d{3})')
LLM_ENDPOINTS = ("/api/v1/cognify", "/api/v1/improve", "/api/v1/remember", "/api/v1/memify")


def available() -> bool:
    return bool(config.DOCKER_PROXY_URL)


def _get(path: str, **kw):
    r = httpx.get(config.DOCKER_PROXY_URL + path, timeout=kw.pop("timeout", 15), **kw)
    r.raise_for_status()
    return r


def containers(project: str | None = None) -> list[dict]:
    if not available():
        return []
    flt = quote(json.dumps({"label": [f"com.docker.compose.project={project or config.STACK_PROJECT}"]}))
    out = []
    for c in _get(f"/containers/json?all=1&filters={flt}").json():
        cid = c["Id"]
        try:
            j = _get(f"/containers/{cid}/json").json()
            st = j.get("State", {})
            nets = {n: v.get("IPAddress") for n, v in (j.get("NetworkSettings", {}).get("Networks") or {}).items()}
            item = {"id": cid[:12], "full_id": cid, "name": c["Names"][0].lstrip("/"), "service": c["Labels"].get("com.docker.compose.service"),
                    "image": j.get("Config", {}).get("Image"), "state": st.get("Status"), "health": (st.get("Health") or {}).get("Status"),
                    "restarts": j.get("RestartCount"), "started": st.get("StartedAt"), "ips": nets,
                    "exit_code": st.get("ExitCode"), "oom_killed": st.get("OOMKilled")}
            if st.get("Status") == "running":
                s = _get(f"/containers/{cid}/stats?stream=false&one-shot=true", timeout=20).json()
                cpu, pre = s["cpu_stats"], s.get("precpu_stats", {})
                dcpu = cpu["cpu_usage"]["total_usage"] - pre.get("cpu_usage", {}).get("total_usage", 0)
                dsys = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
                item["cpu_pct"] = round(100 * dcpu / dsys * cpu.get("online_cpus", 1), 1) if dsys > 0 else None
                mem = s.get("memory_stats", {})
                item["mem_bytes"] = max(mem.get("usage", 0) - mem.get("stats", {}).get("inactive_file", 0), 0)
                item["mem_limit"] = mem.get("limit")
            out.append(item)
        except (httpx.HTTPError, KeyError):
            out.append({"id": cid[:12], "full_id": cid, "name": c["Names"][0].lstrip("/"), "service": c["Labels"].get("com.docker.compose.service"), "state": c.get("State")})
    return sorted(out, key=lambda x: x.get("service") or "")


def demux(raw: bytes) -> list[str]:
    """Docker multiplexa stdout/stderr en tramas de 8 bytes de cabecera + carga."""
    lines, i = [], 0
    while i + 8 <= len(raw):
        size = struct.unpack(">I", raw[i + 4:i + 8])[0]
        chunk = raw[i + 8:i + 8 + size]
        lines.extend(chunk.decode("utf-8", "replace").splitlines())
        i += 8 + size
    return lines


def normalize(path: str) -> str:
    path = path.split("?")[0]
    return _UUID.sub("{id}", path)


def parse_access(lines, ip_names: dict[str, str]) -> dict:
    ep: dict = collections.defaultdict(lambda: {"count": 0, "errors": 0, "last": None, "callers": collections.Counter()})
    callers = collections.Counter()
    status = collections.Counter()
    buckets: collections.Counter = collections.Counter()
    total = health = 0
    for line in lines:
        m = _LINE.match(line)
        if not m:
            continue
        ts, ip, method, path, code = m.groups()
        npath = normalize(path)
        caller = ip_names.get(ip) or ("Mac (hooks, scripts, tu navegador)" if ip.endswith(".1") else ip)
        if npath == "/health":
            health += 1
            continue
        total += 1
        e = ep[(method, npath)]
        e["count"] += 1
        e["errors"] += code[0] in "45"
        e["last"] = ts
        e["callers"][caller] += 1
        callers[caller] += 1
        status[code[0] + "xx"] += 1
        buckets[ts[:13] + ":00"] += 1
    rows = [{"method": m, "path": p, "count": v["count"], "errors": v["errors"], "last": v["last"],
             "llm": p in LLM_ENDPOINTS, "callers": dict(v["callers"].most_common(3))} for (m, p), v in ep.items()]
    return {"total": total, "health_checks": health, "endpoints": sorted(rows, key=lambda r: -r["count"]),
            "callers": [{"caller": k, "count": v} for k, v in callers.most_common()],
            "status": dict(status), "per_hour": [{"hour": k, "count": v} for k, v in sorted(buckets.items())]}


def api_calls(hours: int = 24) -> dict:
    if not available():
        return {"available": False}
    cs = containers()
    api = next((c for c in cs if c.get("service") == "agents_cognee_api"), None)
    if not api:
        return {"available": True, "error": "No se encontró el contenedor de la API"}
    # nombres de los orígenes: contenedores del stack y de esta propia UI (otro proyecto Compose)
    ip_names = {ip: c["service"] for c in cs for ip in (c.get("ips") or {}).values() if ip}
    for c in containers("management_memory"):
        for ip in (c.get("ips") or {}).values():
            if ip:
                ip_names[ip] = f"Management Memory ({c['service']})"
    since = int(time.time() - hours * 3600)
    raw = _get(f"/containers/{api['full_id']}/logs?stdout=1&stderr=1&timestamps=1&since={since}&tail=50000", timeout=60).content
    res = parse_access(demux(raw), ip_names)
    res.update(available=True, hours=hours, container_started=api.get("started"),
               note="Los logs solo cubren desde que arrancó el contenedor de la API (se pierden al recrearlo).")
    return res
