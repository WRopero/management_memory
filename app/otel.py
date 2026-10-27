"""Lectura de la telemetria OTLP (JSON por lineas) que escribe el OTel Collector.

Fuente autoritativa por llamada: eventos `api_request` (logs). Las metricas delta solo concilian.
Los resultados se cachean hasta que cambian los archivos.
"""
from __future__ import annotations

import collections
import datetime as dt
import glob
import json
import os
import statistics
from typing import Any

from . import config

_cache: dict = {"sig": None, "data": None}


def _attrs(items) -> dict:
    out = {}
    for x in items or []:
        v = x.get("value") or {}
        out[x["key"]] = next(iter(v.values())) if v else None
    return out


def _num(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def _iso(nano) -> str | None:
    try:
        return dt.datetime.fromtimestamp(int(nano) / 1e9, dt.timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return None


def files() -> list[dict]:
    out = []
    for p in sorted(glob.glob(os.path.join(config.TELEMETRY_DIR, "otlp*.json*"))):
        try:
            st = os.stat(p)
            out.append({"name": os.path.basename(p), "bytes": st.st_size,
                        "modified": dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc).isoformat(timespec="seconds")})
        except OSError:
            pass
    return out


def parse_lines(lines) -> dict:
    calls: list[dict] = []
    events: collections.Counter = collections.Counter()
    metrics: dict = collections.defaultdict(float)
    resources: dict = {}
    bad = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        for rl in doc.get("resourceLogs", []):
            res = _attrs(rl.get("resource", {}).get("attributes"))
            for sl in rl.get("scopeLogs", []):
                for lr in sl.get("logRecords", []):
                    a = _attrs(lr.get("attributes"))
                    name = a.get("event.name") or "(sin nombre)"
                    events[name] += 1
                    if name != "api_request":
                        continue
                    i, o = _num(a.get("input_tokens")), _num(a.get("output_tokens"))
                    cr, cc = _num(a.get("cache_read_tokens")), _num(a.get("cache_creation_tokens"))
                    known = [v for v in (i, o, cr, cc) if v is not None]
                    calls.append({
                        "ts": _iso(lr.get("timeUnixNano")), "project": res.get("project_id"), "run": res.get("run_id"),
                        "variant": res.get("variant"), "actor": res.get("actor", "main_agent"),
                        "session": a.get("session.id"), "model": a.get("model"),
                        "input": i, "output": o, "cache_read": cr, "cache_creation": cc,
                        "total": sum(known) if known else None,
                        "cost": float(a["cost_usd"]) if a.get("cost_usd") not in (None, "") else None,
                        "duration_ms": _num(a.get("duration_ms")),
                    })
        for rm in doc.get("resourceMetrics", []):
            res = _attrs(rm.get("resource", {}).get("attributes"))
            for sm in rm.get("scopeMetrics", []):
                for m in sm.get("metrics", []):
                    if m.get("name") != "claude_code.token.usage":
                        continue
                    for p in (m.get("sum") or {}).get("dataPoints", []):
                        a = _attrs(p.get("attributes"))
                        v = float(p.get("asInt") or p.get("asDouble") or 0)
                        metrics[(res.get("run_id") or "-", a.get("type") or "?")] += v
        resources_seen = _attrs(doc.get("resourceLogs", [{}])[0].get("resource", {}).get("attributes")) if doc.get("resourceLogs") else {}
        if resources_seen.get("service.version"):
            resources["claude_code"] = resources_seen["service.version"]
    return {"calls": calls, "events": events, "metrics": metrics, "bad_lines": bad, "versions": resources}


def load() -> dict:
    fl = files()
    sig = tuple((f["name"], f["bytes"], f["modified"]) for f in fl)
    if _cache["sig"] == sig and _cache["data"] is not None:
        return _cache["data"]
    lines: list[str] = []
    for f in fl:
        try:
            with open(os.path.join(config.TELEMETRY_DIR, f["name"]), encoding="utf-8", errors="replace") as fh:
                lines.extend(fh.readlines())
        except OSError:
            pass
    data = parse_lines(lines)
    data["files"] = fl
    _cache.update(sig=sig, data=data)
    return data


def _agg(rows: list[dict], key) -> list[dict]:
    g: dict = collections.OrderedDict()
    for r in rows:
        g.setdefault(key(r), []).append(r)
    out = []
    for k, items in g.items():
        durs = [r["duration_ms"] for r in items if r["duration_ms"] is not None]
        s = lambda f: sum(r[f] or 0 for r in items)  # noqa: E731
        out.append({"key": k, "calls": len(items), "input": s("input"), "output": s("output"),
                    "cache_read": s("cache_read"), "cache_creation": s("cache_creation"), "total": s("total"),
                    "cost": round(s("cost"), 5), "p50_ms": int(statistics.median(durs)) if durs else None,
                    "unknown": sum(1 for r in items if r["total"] is None)})
    return out


def summary(days: int | None = None, project: str | None = None) -> dict:
    d = load()
    rows = d["calls"]
    if days:
        cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
        rows = [r for r in rows if (r["ts"] or "") >= cut]
    if project:
        rows = [r for r in rows if r["project"] == project]
    by_run = _agg(rows, lambda r: (r["project"], r["run"], r["variant"], r["actor"]))
    for x in by_run:
        x["project"], x["run"], x["variant"], x["actor"] = x.pop("key")
    by_day = _agg(rows, lambda r: (r["ts"] or "")[:10] or "?")
    for x in by_day:
        x["day"] = x.pop("key")
    by_model = _agg(rows, lambda r: r["model"] or "?")
    for x in by_model:
        x["model"] = x.pop("key")
    logs: dict = collections.defaultdict(lambda: collections.Counter())
    for r in d["calls"]:
        for kind, f in (("input", "input"), ("output", "output"), ("cacheRead", "cache_read"), ("cacheCreation", "cache_creation")):
            logs[r["run"] or "-"][kind] += r[f] or 0
    recon = []
    for run, c in logs.items():
        for kind, lv in c.items():
            mv = d["metrics"].get((run, kind))
            recon.append({"run": run, "kind": kind, "logs": lv, "metrics": mv,
                          "diff_pct": round(100 * ((mv or 0) - lv) / lv, 1) if lv and mv is not None else None})
    total = {k: sum(r[k] or 0 for r in rows) for k in ("input", "output", "cache_read", "cache_creation", "total")}
    total.update(calls=len(rows), cost=round(sum(r["cost"] or 0 for r in rows), 5),
                 sessions=len({r["session"] for r in rows if r["session"]}),
                 unknown=sum(1 for r in rows if r["total"] is None))
    return {"total": total, "by_run": by_run, "by_day": sorted(by_day, key=lambda x: x["day"]), "by_model": by_model,
            "events": [{"name": k, "count": v} for k, v in d["events"].most_common(25)],
            "reconciliation": sorted(recon, key=lambda x: (x["run"], x["kind"])),
            "files": d["files"], "bad_lines": d["bad_lines"], "versions": d["versions"],
            "projects": sorted({r["project"] for r in d["calls"] if r["project"]}),
            "latest": max((r["ts"] for r in d["calls"] if r["ts"]), default=None),
            "recent_calls": sorted(rows, key=lambda r: r["ts"] or "", reverse=True)[:40]}
