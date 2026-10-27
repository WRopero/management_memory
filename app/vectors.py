"""Que vectores se crean y donde: una tabla pgvector por (tipo, campo) dentro del esquema ds_<dataset>."""
from __future__ import annotations

import re

from psycopg import sql

from . import pg

_TYPE_NOTES = {
    "DocumentChunk_text": "Fragmentos del documento (lo que devuelve la búsqueda CHUNKS)",
    "TextSummary_text": "Resumen de cada fragmento (1 llamada LLM por chunk)",
    "TextDocument_name": "Nombre de cada documento",
    "Entity_name": "Entidades extraídas por el LLM (grafo)",
    "EntityType_name": "Tipos de entidad (grafo)",
    "EdgeType_relationship_name": "Tipo de relación de cada arista (grafo): suele ser la colección más pesada",
    "SessionQAVector_text": "Preguntas/respuestas de sesiones guardadas en el grafo",
}


def collections(schema: str) -> list[dict]:
    out = []
    with pg.connect() as con, con.cursor() as cur:
        cur.execute("""select table_name, column_name from information_schema.columns
                       where table_schema=%s and udt_name='vector' order by table_name""", (schema,))
        cols = cur.fetchall()
        for table, col in cols:
            ident = (sql.Identifier(schema), sql.Identifier(table), sql.Identifier(col))
            cur.execute(sql.SQL("select count(*), min(vector_dims({c})) from {s}.{t}").format(c=ident[2], s=ident[0], t=ident[1]))
            rows, dim = cur.fetchone()
            cur.execute("select pg_total_relation_size(format('%%I.%%I', %s::text, %s::text)::regclass), "
                        "pg_relation_size(format('%%I.%%I', %s::text, %s::text)::regclass)", (schema, table, schema, table))
            total, heap = cur.fetchone()
            cur.execute("""select i.indexname, left(i.indexdef, 160), pg_relation_size(format('%%I.%%I', i.schemaname, i.indexname)::regclass)
                           from pg_indexes i where i.schemaname=%s and i.tablename=%s order by 1""", (schema, table))
            idx = [{"name": n, "def": d, "bytes": int(b), "ann": bool(re.search(r"hnsw|ivfflat", d, re.I))} for n, d, b in cur.fetchall()]
            sample = None
            if rows and _has_payload(cur, schema, table):
                cur.execute(sql.SQL("select {c}::text, payload->>'text', payload->>'name' from {s}.{t} limit 1").format(
                    c=ident[2], s=ident[0], t=ident[1]))
                got = cur.fetchone()
                if got:
                    comps = [float(x) for x in got[0].strip("[]").split(",")[:6]]
                    sample = {"first_components": [round(c, 4) for c in comps], "item": (got[1] or got[2] or "")[:90]}
            kind, _, field = table.partition("_")
            out.append({"table": table, "type": kind, "field": field or col, "rows": rows, "dim": dim, "bytes_total": int(total),
                        "bytes_data": int(heap), "bytes_vectors_est": (rows or 0) * (dim or 0) * 4, "indexes": idx,
                        "has_ann_index": any(i["ann"] for i in idx), "sample": sample,
                        "note": _TYPE_NOTES.get(table, "")})
    return sorted(out, key=lambda c: -c["bytes_total"])


def _has_payload(cur, schema, table) -> bool:
    cur.execute("select 1 from information_schema.columns where table_schema=%s and table_name=%s and column_name='payload'", (schema, table))
    return cur.fetchone() is not None
