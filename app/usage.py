"""Uso de la memoria: cuándo se consulta y cómo (eventos extraídos por `usage_scan.py` de los transcripts de Claude Code).

Solo metadatos: query truncada, dataset, ok/error, latencia y tamaño del resultado. Solo lectura.
"""
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

from . import config


def _events() -> list[dict]:
    try:
        with open(config.USAGE_FILE, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]
    except (OSError, json.JSONDecodeError):
        return []


def _day(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).astimezone().strftime("%Y-%m-%d")


def summary(days: int = 14, project: str | None = None) -> dict:
    evs = _events()
    since = time.time() - days * 86400
    evs = [e for e in evs if e["ts"] >= since and (not project or e.get("project") == project)]
    by_kind = Counter(e["kind"] for e in evs)
    recalls = [e for e in evs if e["kind"] == "recall"]
    mcp = [e for e in recalls if e.get("via") == "mcp"]
    answered = [e for e in mcp if "ok" in e]
    ok = [e for e in answered if e["ok"]]
    lat = sorted(e["latency_s"] for e in answered if e.get("latency_s") is not None)
    sessions = {e["session"] for e in evs}
    with_briefing = {e["session"] for e in evs if e["kind"] == "briefing"}
    with_recall = {e["session"] for e in recalls}
    plug = [e for e in evs if e["kind"] == "plugin" and e.get("asked")]
    per_day = defaultdict(lambda: Counter())
    for e in evs:
        per_day[_day(e["ts"])][e["kind"]] += 1
    errors = [e for e in answered if not e["ok"]]
    return {
        "days": days, "file_present": bool(_events()), "events": len(evs),
        "sessions": {"total": len(sessions), "with_briefing": len(with_briefing), "with_recall": len(with_recall)},
        "counts": dict(by_kind),
        "recall": {"total": len(recalls), "via_mcp": len(mcp), "via_skill": len(recalls) - len(mcp), "answered": len(answered), "ok": len(ok),
                   "errors": len(errors), "p50_s": lat[len(lat) // 2] if lat else None,
                   "avg_chars": round(sum(e.get("chars", 0) for e in ok) / len(ok)) if ok else None},
        "briefing": {"count": by_kind.get("briefing", 0),
                     "avg_chars": round(sum(e.get("chars", 0) for e in evs if e["kind"] == "briefing") / by_kind["briefing"]) if by_kind.get("briefing") else None},
        "plugin": {"hits": sum(e["hits"] or 0 for e in plug), "asked": sum(e["asked"] or 0 for e in plug)},
        "per_day": [{"day": d, **dict(c)} for d, c in sorted(per_day.items())],
        "recent": [{**e, "when": datetime.fromtimestamp(e["ts"], timezone.utc).astimezone().isoformat(timespec="seconds")}
                   for e in reversed(evs) if e["kind"] in ("recall", "write", "briefing")][:60],
        "projects": sorted({e.get("project") for e in _events() if e.get("project")}),
    }
