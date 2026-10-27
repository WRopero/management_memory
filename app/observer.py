"""Observer (claude -p) y registro de sincronizacion."""
from __future__ import annotations

import collections
import datetime as dt
import json
import os
import statistics

import httpx

from . import config


def health() -> dict:
    try:
        r = httpx.get(f"{config.OBSERVER_URL}/health", timeout=3)
        return {"ok": r.status_code == 200, **r.json()}
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "error": str(exc)[:120]}


def parse_events(lines) -> list[dict]:
    out = []
    for line in lines:
        try:
            e = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        d = e.get("detail") or {}
        out.append({"ts": e.get("ts"), "event": e.get("event"), "model": d.get("model"),
                    "duration_ms": d.get("duration_ms"), "tokens": d.get("tokens"), "detail": d})
    return out


def summary(days: int = 14) -> dict:
    try:
        with open(config.OBSERVER_LOG, encoding="utf-8", errors="replace") as fh:
            events = parse_events(fh.readlines())
    except OSError:
        return {"available": False, "by_day": [], "recent": [], "total": {}}
    comps = [e for e in events if e["event"] == "completion"]
    cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT")
    by_day: dict = collections.OrderedDict()
    for e in comps:
        day = (e["ts"] or "")[:10]
        b = by_day.setdefault(day, {"day": day, "calls": 0, "tokens": 0, "durations": []})
        b["calls"] += 1
        b["tokens"] += e["tokens"] or 0
        if e["duration_ms"]:
            b["durations"].append(e["duration_ms"])
    days_list = []
    for b in by_day.values():
        ds = b.pop("durations")
        b["p50_ms"] = int(statistics.median(ds)) if ds else None
        days_list.append(b)
    durs = [e["duration_ms"] for e in comps if e["duration_ms"]]
    other = collections.Counter(e["event"] for e in events if e["event"] != "completion")
    return {"available": True, "by_day": days_list,
            "total": {"calls": len(comps), "tokens": sum(e["tokens"] or 0 for e in comps),
                      "p50_ms": int(statistics.median(durs)) if durs else None,
                      "p95_ms": int(sorted(durs)[max(int(len(durs) * 0.95) - 1, 0)]) if durs else None,
                      "avg_tokens": int(sum(e["tokens"] or 0 for e in comps) / len(comps)) if comps else 0},
            "other_events": [{"event": k, "count": v} for k, v in other.most_common(10)],
            "recent": [{k: e[k] for k in ("ts", "model", "duration_ms", "tokens")} for e in comps[-40:]][::-1]}


def registry() -> list[dict]:
    try:
        with open(config.REGISTRY_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    rows = []
    for project, docs in data.items():
        for path, e in docs.items():
            rows.append({"project": project, "path": path, "doc_id": e.get("doc_id"), "status": e.get("status"),
                         "data_id": e.get("data_id"), "hash": (e.get("hash") or "")[:12], "commit": e.get("commit"),
                         "embedder": e.get("embedder"), "updated": e.get("updated"), "last_error": e.get("last_error") or ""})
    return rows
