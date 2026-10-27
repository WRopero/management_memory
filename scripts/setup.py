#!/usr/bin/env python3
"""Prepara Management Memory (idempotente, sin imprimir secretos):
  1. crea .env con una API key propia de Cognee y la contraseña de un rol de Postgres de solo lectura;
  2. crea/actualiza el rol `mm_reader` en el Postgres del stack (SCRAM calculado aqui: no viaja en claro);
  3. copia del registro de sincronizacion al directorio `view/` que se monta en solo lectura.
Uso: setup.py [--stack-dir ~/Documents/Developer/agents_memory_system]
"""
import argparse, base64, hashlib, hmac, json, os, re, secrets, shutil, string, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--stack-dir", default=str(Path.home() / "Documents/Developer/agents_memory_system"))
a = ap.parse_args()
stack = Path(a.stack_dir).expanduser()
env_path = ROOT / ".env"


def read_env(p: Path) -> dict:
    out = {}
    if p.exists():
        for ln in p.read_text().splitlines():
            if "=" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.split("=", 1); out[k.strip()] = v.strip()
    return out


def scram(pw: str, it: int = 4096) -> str:
    salt = os.urandom(16); salted = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, it)
    ck = hmac.new(salted, b"Client Key", "sha256").digest(); sk = hmac.new(salted, b"Server Key", "sha256").digest()
    b = lambda x: base64.b64encode(x).decode()
    return f"SCRAM-SHA-256${it}:{b(salt)}${b(hashlib.sha256(ck).digest())}:{b(sk)}"


stack_env = read_env(stack / "deploy/docker/.env")
if not stack_env:
    sys.exit(f"No encuentro {stack}/deploy/docker/.env: ¿el stack agents_memory_system está instalado?")
env = read_env(env_path)

# 1) API key de Cognee (revocable)
if not env.get("COGNEE_API_KEY"):
    req = urllib.request.Request("http://127.0.0.1:45874/api/v1/auth/login", method="POST",
        data=urllib.parse.urlencode({"username": stack_env["COGNEE_USER_EMAIL"], "password": stack_env["COGNEE_USER_PASSWORD"]}).encode())
    token = json.load(urllib.request.urlopen(req, timeout=15))["access_token"]
    req = urllib.request.Request("http://127.0.0.1:45874/api/v1/auth/api-keys", method="POST",
        data=json.dumps({"name": "management-memory"}).encode(), headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    env["COGNEE_API_KEY"] = json.load(urllib.request.urlopen(req, timeout=15))["key"]
    print("API key de Cognee creada (guardada en .env)")
# 2) rol de solo lectura
newpw = False
if not env.get("INSPECTOR_PG_PASSWORD"):
    env["INSPECTOR_PG_PASSWORD"] = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(40)); newpw = True
env.setdefault("INSPECTOR_PG_USER", "mm_reader")
env.setdefault("INSPECTOR_PG_DB", "agents_memory")
ctr = subprocess.run(["docker", "ps", "-q", "--filter", "label=com.docker.compose.project=agents_memory_system",
                      "--filter", "label=com.docker.compose.service=agents_postgres"], capture_output=True, text=True).stdout.split()
if not ctr:
    sys.exit("El contenedor agents_postgres no está corriendo")
user = env["INSPECTOR_PG_USER"]
sqlt = f"""
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{user}') THEN CREATE ROLE {user} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE; END IF;
END $$;
ALTER ROLE {user} PASSWORD '{scram(env["INSPECTOR_PG_PASSWORD"])}';
GRANT pg_read_all_data TO {user};
ALTER ROLE {user} SET default_transaction_read_only = on;
ALTER ROLE {user} SET statement_timeout = '15s';
"""
r = subprocess.run(["docker", "exec", "-i", ctr[0], "psql", "-U", stack_env.get("AGENTS_PG_USER", "agents"), "-d", "agents_memory",
                    "-v", "ON_ERROR_STOP=1", "-q", "-f", "-"], input=sqlt, capture_output=True, text=True)
if r.returncode:
    sys.exit("Fallo al crear el rol: " + r.stderr[-300:])
print(f"rol {user} listo (pg_read_all_data, solo lectura, timeout 15 s)")
env_path.write_text("".join(f"{k}={v}\n" for k, v in env.items())); os.chmod(env_path, 0o600)
# 3) copia legible del registro de sincronizacion
view = Path.home() / ".local/share/agents_memory_system/view"; view.mkdir(parents=True, exist_ok=True)
reg = Path.home() / ".local/share/agents_memory_system/registry.json"
if reg.exists():
    shutil.copy2(reg, view / "registry.json"); print("registro copiado a", view)
print("Listo. Siguiente: docker compose up -d --build  →  http://127.0.0.1:45876")
