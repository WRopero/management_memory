"""Acceso de SOLO LECTURA a PostgreSQL (rol agents_inspector: pg_read_all_data, read-only, timeout)."""
from __future__ import annotations

import datetime as dt
import decimal
import re
import uuid
from typing import Any

import psycopg
from psycopg import sql

from . import config

MAX_ROWS = 500
_READONLY_START = ("select", "with", "explain", "show", "values", "table")
_SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")


class QueryRejected(ValueError):
    pass


def connect() -> psycopg.Connection:
    return psycopg.connect(
        **config.PG, autocommit=True, connect_timeout=5,
        options="-c default_transaction_read_only=on -c statement_timeout=15000 -c idle_in_transaction_session_timeout=15000",
    )


def fmt(value: Any, type_name: str = "") -> Any:
    """Convierte un valor a algo serializable y corto (vectores y textos largos se resumen)."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<bytes {len(bytes(value))}>"
    if isinstance(value, (list, dict)):
        s = str(value)
    else:
        s = str(value)
    if type_name == "vector" or (s.startswith("[") and s.count(",") > 40 and len(s) > 200):
        return f"<vector dim={s.count(',') + 1}>"
    return s if len(s) <= 300 else f"{s[:300]}… (+{len(s) - 300} car.)"


def validate_query(text: str) -> str:
    q = (text or "").strip()
    q = q[:-1].strip() if q.endswith(";") else q
    if not q:
        raise QueryRejected("La consulta está vacía")
    if ";" in q:
        raise QueryRejected("Solo se permite una sentencia")
    if not q.lower().lstrip("( ").startswith(_READONLY_START):
        raise QueryRejected("Solo consultas de lectura (SELECT, WITH, EXPLAIN, SHOW, VALUES, TABLE)")
    return q


def _rows(cur, limit: int) -> dict:
    cols = [d.name for d in cur.description or []]
    types = [d.type_code for d in cur.description or []]
    data = cur.fetchmany(limit + 1)
    truncated = len(data) > limit
    return {"columns": cols, "rows": [[fmt(v) for v in row] for row in data[:limit]], "truncated": truncated,
            "types": [str(t) for t in types]}


def run_query(text: str, limit: int = MAX_ROWS) -> dict:
    q = validate_query(text)
    with connect() as con, con.cursor() as cur:
        cur.execute(q)
        return _rows(cur, min(limit, MAX_ROWS))


def overview() -> dict:
    with connect() as con, con.cursor() as cur:
        cur.execute("select version(), pg_database_size(current_database()), current_user, "
                    "(select count(*) from pg_stat_activity where datname = current_database())")
        v, size, user, conns = cur.fetchone()
    return {"ok": True, "version": v.split(",")[0], "size_bytes": size, "user": user, "connections": conns}


def schemas() -> list[dict]:
    q = """
    select n.nspname,
           count(c.oid) filter (where c.relkind in ('r','p')) as tables,
           coalesce(sum(pg_total_relation_size(c.oid)) filter (where c.relkind in ('r','p')), 0) as bytes
    from pg_namespace n left join pg_class c on c.relnamespace = n.oid
    where n.nspname not like 'pg_%%' and n.nspname <> 'information_schema'
    group by n.nspname order by (n.nspname like 'ds_%%'), n.nspname"""
    with connect() as con, con.cursor() as cur:
        cur.execute(q)
        return [{"schema": s, "tables": t, "bytes": int(b)} for s, t, b in cur.fetchall()]


def _ensure_table(cur, schema: str, table: str) -> None:
    cur.execute("select 1 from information_schema.tables where table_schema=%s and table_name=%s", (schema, table))
    if not cur.fetchone():
        raise QueryRejected("La tabla no existe")


def tables(schema: str, exact: bool = True) -> list[dict]:
    with connect() as con, con.cursor() as cur:
        cur.execute("""select c.relname, pg_total_relation_size(c.oid), c.reltuples::bigint
                       from pg_class c join pg_namespace n on n.oid=c.relnamespace
                       where n.nspname=%s and c.relkind in ('r','p') order by c.relname""", (schema,))
        out = [{"table": t, "bytes": int(b), "estimate": max(int(e), 0), "rows": None} for t, b, e in cur.fetchall()]
        if exact:
            for item in out:
                try:
                    cur.execute(sql.SQL("select count(*) from {}.{}").format(sql.Identifier(schema), sql.Identifier(item["table"])))
                    item["rows"] = cur.fetchone()[0]
                except psycopg.Error:
                    item["rows"] = None
    return out


def table_detail(schema: str, table: str, limit: int = 50, offset: int = 0) -> dict:
    limit = max(1, min(limit, 200))
    with connect() as con, con.cursor() as cur:
        _ensure_table(cur, schema, table)
        cur.execute("""select column_name, data_type, udt_name, is_nullable from information_schema.columns
                       where table_schema=%s and table_name=%s order by ordinal_position""", (schema, table))
        columns = [{"name": n, "type": u if d == "USER-DEFINED" else d, "nullable": nl == "YES"} for n, d, u, nl in cur.fetchall()]
        cur.execute(sql.SQL("select * from {}.{} limit %s offset %s").format(sql.Identifier(schema), sql.Identifier(table)),
                    (limit, max(offset, 0)))
        names = [d.name for d in cur.description]
        tmap = {c["name"]: c["type"] for c in columns}
        rows = [[fmt(v, tmap.get(n, "")) for v, n in zip(row, names)] for row in cur.fetchall()]
    return {"columns": columns, "rows": rows, "limit": limit, "offset": offset}


def dataset_schema_name(dataset_id: str) -> str:
    return "ds_" + re.sub(r"[^0-9a-f]", "", dataset_id.lower())
