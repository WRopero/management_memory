"""Recursos del equipo: el Mac (muestras de `host_stats.py`) y Docker (motor, VM, contenedores, disco). Solo lectura."""
import time

import httpx

from . import config, dockerapi


_history: list[dict] = []   # mediciones de esta sesion del panel (en memoria; nada se escribe a disco)
_last: dict | None = None


def measure_host() -> dict:
    """Pide UNA medicion del Mac al disparador bajo demanda de launchd (host_stats.py --inetd)."""
    global _last
    try:
        r = httpx.post(config.HOST_AGENT_URL + "/", headers={"Host": "host.docker.internal:8018"}, timeout=20)
        r.raise_for_status()
        s = r.json()
    except (httpx.HTTPError, ValueError) as e:
        return {"available": False, "error": "El disparador del Mac no responde. Instálalo con: scripts/host_stats_launchagent.sh install (" + str(e)[:120] + ")"}
    _last = s
    _history.append({"ts": s["ts"], "cpu": (s.get("cpu") or {}).get("used"), "mem_used": s["memory"]["used"], "swap_used": s["memory"]["swap_used"]})
    del _history[:-120]
    return host()


def host() -> dict:
    if not _last:
        return {"available": False, "measured": False}
    return {"available": True, "measured": True, "age_s": round(time.time() - _last["ts"]), "latest": _last, "history": list(_history)}


def docker() -> dict:
    if not dockerapi.available():
        return {"available": False}
    try:
        info = dockerapi._get("/info").json()
        df = dockerapi._get("/system/df", timeout=40).json()
    except (httpx.HTTPError, ValueError) as e:
        return {"available": False, "error": str(e)[:200]}
    conts = []
    for project in ("agents_memory_system", config.STACK_PROJECT, "management_memory"):
        for c in dockerapi.containers(project):
            if c["name"] not in {x["name"] for x in conts}:
                conts.append(c)
    running = [c for c in conts if c.get("state") == "running"]
    vols = sorted(({"name": v["Name"], "bytes": (v.get("UsageData") or {}).get("Size", -1)} for v in df.get("Volumes") or []), key=lambda v: -v["bytes"])
    images = df.get("Images") or []
    return {
        "available": True,
        "engine": {"version": info.get("ServerVersion"), "os": info.get("OperatingSystem"), "cpus": info.get("NCPU"), "mem_total": info.get("MemTotal"),
                   "containers": info.get("Containers"), "running": info.get("ContainersRunning"), "images": info.get("Images")},
        "usage": {"cpu_pct_sum": round(sum(c.get("cpu_pct") or 0 for c in running), 1), "mem_used": sum(c.get("mem_bytes") or 0 for c in running)},
        "containers": [{k: c.get(k) for k in ("name", "service", "state", "health", "cpu_pct", "mem_bytes", "mem_limit", "restarts")} for c in conts],
        "disk": {"images_bytes": sum(i.get("Size", 0) for i in images), "images": len(images),
                 "containers_bytes": sum((c.get("SizeRw") or 0) for c in df.get("Containers") or []),
                 "volumes_bytes": sum(v["bytes"] for v in vols if v["bytes"] > 0),
                 "build_cache_bytes": sum(b.get("Size", 0) for b in df.get("BuildCache") or []), "volumes": vols[:12]},
    }
