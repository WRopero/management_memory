"""Bases de conocimiento por proyecto: tamaño, costo de reingesta y candidatos a compactar o eliminar."""
from __future__ import annotations

import collections
import re
import statistics

from . import cognee_client as cognee
from . import config, observer, pg, storage, vectors

_AVG_TOKENS_PER_CALL_FALLBACK = 4000


def classify(name: str) -> tuple[str, str]:
    """(proyecto, tipo) a partir del nombre del dataset: <proyecto>-knowledge | <proyecto>_sessions | codebase-<repo>-<hash>.
    El proyecto se normaliza (guion bajo = guion) para agrupar datasets con separadores distintos."""
    norm = lambda x: x.replace("_", "-").lower()  # noqa: E731
    if name.endswith("-knowledge"):
        return norm(name[: -len("-knowledge")]), "conocimiento"
    if name.endswith("_sessions") or name.endswith("-sessions"):
        return norm(name[: -len("_sessions")]), "sesiones"
    m = re.match(r"codebase-(.+)-[0-9a-f]{6,}$", name)
    if m:
        return norm(m.group(1)), "código"
    return norm(name), "otro"


def _avg_tokens_per_call() -> int:
    t = observer.summary().get("total", {})
    return int(t.get("avg_tokens") or _AVG_TOKENS_PER_CALL_FALLBACK)


def _chunks_by_doc(schema: str) -> dict[str, dict]:
    try:
        with pg.connect() as con, con.cursor() as cur:
            cur.execute(f'select payload->>\'document_id\', count(*), coalesce(sum(length(payload->>\'text\')),0) '
                        f'from "{schema}"."DocumentChunk_text" group by 1')
            return {d: {"chunks": c, "chars": int(ch)} for d, c, ch in cur.fetchall()}
    except Exception:
        return {}


def dataset_report(ds: dict, graph_files: dict, summaries: dict, avg_tokens: int, registry_rows: list[dict]) -> dict:
    did, name = ds["id"], ds["name"]
    project, kind = classify(name)
    schema = pg.dataset_schema_name(did)
    docs = cognee.get(f"/api/v1/datasets/{did}/data") or []
    by_doc = _chunks_by_doc(schema)
    try:
        cols = vectors.collections(schema)
    except Exception:
        cols = []
    pg_bytes = sum(s["bytes"] for s in pg.schemas() if s["schema"] == schema)
    chunks = sum(v["chunks"] for v in by_doc.values())
    chars = sum(v["chars"] for v in by_doc.values())
    vec_rows = sum(c["rows"] or 0 for c in cols)
    vec_bytes = sum(c["bytes_total"] for c in cols)
    gf = graph_files.get(did, {})
    g = summaries.get(did, {})
    reg = {r["data_id"]: r for r in registry_rows if r.get("data_id")}
    est_calls = chunks * 2
    doc_rows = []
    for d in docs:
        c = by_doc.get(d["id"], {"chunks": 0, "chars": 0})
        r = reg.get(d["id"], {})
        doc_rows.append({"id": d["id"], "name": d.get("name"), "path": r.get("path"), "doc_id": r.get("doc_id"),
                         "status": r.get("status"), "bytes": d.get("dataSize"), "chunks": c["chunks"], "chars": c["chars"],
                         "est_tokens": int(c["chars"] / config.CHARS_PER_TOKEN),
                         "est_reingest_tokens": c["chunks"] * 2 * avg_tokens, "created": d.get("createdAt"),
                         "updated": r.get("updated")})
    flags = _flags(name, kind, doc_rows, reg, cols, registry_rows, project)
    footprint = pg_bytes + gf.get("bytes", 0) + gf.get("wal_bytes", 0) + sum(d["bytes"] or 0 for d in doc_rows)
    return {"id": did, "name": name, "project": project, "kind": kind, "schema": schema, "documents": len(docs),
            "raw_bytes": sum(d["bytes"] or 0 for d in doc_rows), "chunks": chunks, "chunk_chars": chars,
            "est_tokens": int(chars / config.CHARS_PER_TOKEN), "nodes": g.get("numNodes"), "edges": g.get("numEdges"),
            "vector_collections": len(cols), "vector_rows": vec_rows, "vector_bytes": vec_bytes, "pg_bytes": pg_bytes,
            "graph_bytes": gf.get("bytes", 0), "graph_wal_bytes": gf.get("wal_bytes", 0), "footprint_bytes": footprint,
            "est_reingest_calls": est_calls, "est_reingest_tokens": est_calls * avg_tokens, "avg_tokens_per_call": avg_tokens,
            "flags": flags, "docs": sorted(doc_rows, key=lambda x: -x["chunks"]), "collections": cols}


def _flags(name, kind, docs, reg, cols, registry_rows, project) -> list[dict]:
    out = []
    if not docs and kind != "sesiones":
        out.append({"level": "info", "code": "vacio", "text": "Dataset sin documentos: candidato a eliminar."})
    if kind == "código" and not docs:
        out.append({"level": "info", "code": "codigo_vacio", "text": "Dataset de código creado por el plugin y vacío (la indexación de código está apagada)."})
    if kind == "sesiones":
        out.append({"level": "info", "code": "sesiones", "text": f"Historia de sesiones: {len(docs)} elementos. Cada cierre de sesión cuesta ~3 llamadas; revisar si compensa."})
    mine = [r for r in registry_rows if r["project"] == project]
    bad = [r for r in mine if r["status"] != "indexed"]
    if bad and kind == "conocimiento":
        out.append({"level": "warn", "code": "no_indexados", "text": f"{len(bad)} documento(s) del registro no están 'indexed' (reintentar con sync)."})
    ids = {d["id"] for d in docs}
    missing = [r for r in mine if r.get("data_id") and r["data_id"] not in ids]
    if missing and kind == "conocimiento":
        out.append({"level": "warn", "code": "faltan_en_cognee", "text": f"{len(missing)} documento(s) del registro no existen en Cognee."})
    orphans = [d for d in docs if d["id"] not in reg]
    if orphans and kind == "conocimiento":
        out.append({"level": "warn", "code": "huerfanos", "text": f"{len(orphans)} documento(s) en Cognee sin entrada en el registro (¿cargados a mano?)."})
    vb = sum(c["bytes_total"] for c in cols)
    edge = next((c for c in cols if c["table"] == "EdgeType_relationship_name"), None)
    if edge and vb and edge["bytes_total"] / vb > 0.4:
        out.append({"level": "tip", "code": "aristas_dominan", "text": f"Los vectores de tipos de relación pesan {round(100 * edge['bytes_total'] / vb)}% de los vectores (cada conexión del grafo genera su propio vector con una frase descriptiva): es la primera candidata si hay que compactar."})
    chunk_counts = [d["chunks"] for d in docs if d["chunks"]]
    if len(chunk_counts) >= 4:
        med = statistics.median(chunk_counts)
        heavy = [d for d in docs if d["chunks"] > max(2 * med, 4)]
        if heavy:
            out.append({"level": "tip", "code": "docs_pesados", "text": f"{len(heavy)} documento(s) con >2× la mediana de chunks (cada chunk ≈ 2 llamadas a Claude): " + ", ".join((d['path'] or d['name'] or '?').split('/')[-1] for d in heavy[:4])})
    if not any(c["has_ann_index"] for c in cols) and cols:
        out.append({"level": "info", "code": "sin_ann", "text": "Sin índice ANN (HNSW/IVFFlat): búsqueda exacta; con corpus pequeños es lo correcto, se vuelve lento a decenas de miles de filas."})
    return out


def overview() -> dict:
    datasets = cognee.get("/api/v1/datasets") or []
    gsum = cognee.get("/api/v1/datasets/graph-summary") or []
    summaries = {g["datasetId"]: g for g in gsum}
    gf = storage.graph_files()
    avg = _avg_tokens_per_call()
    reg = observer.registry()
    reports = [dataset_report(d, gf, summaries, avg, reg) for d in datasets]
    projects: dict = collections.OrderedDict()
    for r in reports:
        p = projects.setdefault(r["project"], {"project": r["project"], "datasets": [], "documents": 0, "chunks": 0,
                                               "footprint_bytes": 0, "est_reingest_tokens": 0, "vector_rows": 0})
        p["datasets"].append({"id": r["id"], "name": r["name"], "kind": r["kind"]})
        for k in ("documents", "chunks", "footprint_bytes", "est_reingest_tokens", "vector_rows"):
            p[k] += r[k] or 0
    for r in reports:  # el detalle pesado se pide por dataset
        r.pop("docs"), r.pop("collections")
    return {"projects": list(projects.values()), "datasets": reports, "storage": storage.totals(), "avg_tokens_per_call": avg,
            "pg": pg.overview()}
