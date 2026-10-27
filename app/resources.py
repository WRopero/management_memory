"""Recursos del equipo: el Mac (muestras de `host_stats.py`) y Docker (motor, VM, contenedores, disco). Solo lectura."""
import json
import time

import httpx

from . import config, dockerapi


def host() -> dict:
    try:
        with open(config.HOST_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"available": False}
    latest = d.get("latest") or {}
    return {"available": True, "age_s": round(time.time() - latest.get("ts", 0)), "latest": latest, "history": d.get("history", [])[-240:]}


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
