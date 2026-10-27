import json
import struct

import pytest

from app import dockerapi, kb, observer, otel, pg


def _otlp(lines):
    return [json.dumps(x) for x in lines]


LOG = {"resourceLogs": [{"resource": {"attributes": [
    {"key": "project_id", "value": {"stringValue": "p1"}}, {"key": "run_id", "value": {"stringValue": "r1"}},
    {"key": "variant", "value": {"stringValue": "B"}}, {"key": "service.version", "value": {"stringValue": "2.1.310"}}]},
    "scopeLogs": [{"logRecords": [
        {"timeUnixNano": "1793041000000000000", "attributes": [
            {"key": "event.name", "value": {"stringValue": "api_request"}}, {"key": "model", "value": {"stringValue": "haiku"}},
            {"key": "input_tokens", "value": {"stringValue": "2"}}, {"key": "output_tokens", "value": {"stringValue": "4"}},
            {"key": "cache_read_tokens", "value": {"stringValue": "100"}}, {"key": "cache_creation_tokens", "value": {"stringValue": "0"}},
            {"key": "cost_usd", "value": {"doubleValue": 0.001}}, {"key": "session.id", "value": {"stringValue": "s1"}}]},
        {"timeUnixNano": "1793041001000000000", "attributes": [{"key": "event.name", "value": {"stringValue": "hook_registered"}}]},
    ]}]}]}
MET = {"resourceMetrics": [{"resource": {"attributes": [{"key": "run_id", "value": {"stringValue": "r1"}}]}, "scopeMetrics": [{"metrics": [
    {"name": "claude_code.token.usage", "sum": {"dataPoints": [
        {"asInt": "80", "attributes": [{"key": "type", "value": {"stringValue": "cacheRead"}}]}]}}]}]}]}


def test_otel_extrae_api_request_y_cuenta_eventos():
    d = otel.parse_lines(_otlp([LOG, MET]) + ["", "{no json"])
    assert len(d["calls"]) == 1 and d["bad_lines"] == 1
    c = d["calls"][0]
    assert (c["total"], c["cost"], c["run"], c["variant"]) == (106, 0.001, "r1", "B")
    assert d["events"]["hook_registered"] == 1
    assert d["metrics"][("r1", "cacheRead")] == 80


def test_otel_total_desconocido_no_es_cero():
    log = json.loads(json.dumps(LOG))
    attrs = log["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]
    log["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"] = [a for a in attrs if "tokens" not in a["key"]]
    assert otel.parse_lines(_otlp([log]))["calls"][0]["total"] is None


def test_observer_parse_events():
    ev = observer.parse_events([json.dumps({"ts": "2026-10-27T01:00:00+00:00", "event": "completion",
                                            "detail": {"model": "haiku", "duration_ms": 5, "tokens": 9}}), "basura"])
    assert ev == [{"ts": "2026-10-27T01:00:00+00:00", "event": "completion", "model": "haiku", "duration_ms": 5, "tokens": 9,
                   "detail": {"model": "haiku", "duration_ms": 5, "tokens": 9}}]


def test_docker_demux_y_access_log():
    payload = b"2026-10-27T18:07:25.1Z 172.19.0.1:6 - \"POST /api/v1/cognify HTTP/1.1\" 200\n"
    raw = b"\x01\x00\x00\x00" + struct.pack(">I", len(payload)) + payload
    lines = dockerapi.demux(raw)
    assert len(lines) == 1
    res = dockerapi.parse_access(lines + ["2026-10-27T18:08:00Z 127.0.0.1:1 - \"GET /health HTTP/1.1\" 200",
                                          "2026-10-27T18:09:00Z 172.19.0.5:2 - \"GET /api/v1/datasets/3efa20eb-bd35-54f9-b57a-4368b6ec1da0/data HTTP/1.1\" 404"],
                                 {"172.19.0.5": "agents_cognee_mcp"})
    assert res["total"] == 2 and res["health_checks"] == 1
    paths = {e["path"]: e for e in res["endpoints"]}
    assert paths["/api/v1/cognify"]["llm"] is True
    assert "/api/v1/datasets/{id}/data" in paths and paths["/api/v1/datasets/{id}/data"]["errors"] == 1
    assert {c["caller"] for c in res["callers"]} == {"Mac (hooks, scripts, tu navegador)", "agents_cognee_mcp"}


@pytest.mark.parametrize("q", ["delete from x", "select 1; drop table x", "update t set a=1", "", "  ;", "insert into t values (1)",
                               "create table t(a int)", "call foo()", "do $$ begin end $$"])
def test_sql_peligroso_se_rechaza(q):
    with pytest.raises(pg.QueryRejected):
        pg.validate_query(q)


@pytest.mark.parametrize("q", ["select 1", "SELECT 1;", "with a as (select 1) select * from a", "explain select 1", "show server_version", "(select 1)"])
def test_sql_de_lectura_se_acepta(q):
    assert pg.validate_query(q)


def test_fmt_resume_vectores_y_textos_largos():
    assert pg.fmt("[" + ",".join(["0.1"] * 768) + "]") == "<vector dim=768>"
    assert pg.fmt("x" * 400).endswith("(+100 car.)")
    assert pg.fmt(b"abc") == "<bytes 3>" and pg.fmt(None) is None


def test_clasificacion_de_datasets_y_esquema():
    assert kb.classify("glf-assistant-knowledge") == ("glf-assistant", "conocimiento")
    assert kb.classify("glf_assistant_sessions") == ("glf-assistant", "sesiones")
    assert kb.classify("codebase-glf_assistant-749bcea1") == ("glf-assistant", "código")
    assert kb.classify("otro") == ("otro", "otro")
    assert pg.dataset_schema_name("3efa20eb-bd35-54f9-b57a-4368b6ec1da0") == "ds_3efa20ebbd3554f9b57a4368b6ec1da0"
