# Management Memory

Panel de control **interno y de solo lectura** para vigilar la memoria de proyecto (Cognee en Docker): salud de los servicios, qué vectores existen y dónde, grafo, PostgreSQL, tokens y costo (observer + OpenTelemetry), llamadas a la API, contenedores y tamaño de la base de conocimiento por proyecto (con avisos para decidir qué compactar o eliminar). No modifica nada.

Corre en `http://127.0.0.1:45876`, solo local.

## Cómo correrlo

Requisitos: Docker Desktop corriendo y el stack de memoria arriba (`~/Documents/Developer/agents_memory_system`, ver `seed-bundle/`).

```bash
cd ~/Documents/Developer/management_memory

# Primera vez (idempotente, no imprime secretos): crea .env, el rol Postgres de solo lectura y la copia del registro
python3 scripts/setup.py

# Levantar (construye la imagen la primera vez)
docker compose up -d --build

open http://127.0.0.1:45876
```

| Acción | Comando |
|---|---|
| Ver logs | `docker compose logs -f mm_app` |
| Parar | `docker compose stop` (nunca `down -v`; no tiene volúmenes propios que perder) |
| Reconstruir tras cambiar código | `docker compose up -d --build mm_app` |
| Tests | `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest` |

Si el navegador muestra una versión vieja tras reconstruir: recarga forzada (`Cmd+Shift+R`).

## Qué muestra cada sección
Resumen · Bases de conocimiento (por proyecto/dataset, costo de reconstruir, documentos que más pesan, avisos) · Vectores (qué se guarda y dónde) · Grafo · PostgreSQL (explorador + consola SELECT) · Búsqueda (prueba de recuperación) · **Uso de la memoria** (cuándo se inyecta el briefing y cuándo se consulta, con resultado y veredicto «¿funciona?») · **Recursos del equipo** (CPU/RAM/swap/disco del Mac y de Docker, en vivo) · Tokens y costo · API y contenedores · Sincronización · Guía y glosario (explica cada concepto en lenguaje llano).

## Datos que vienen del Mac (servicios ligeros, en `agents_memory_system`)
- **Uso de la memoria**: `scripts/usage_scan.py` lee los transcripts de Claude Code (solo lectura, solo metadatos) y escribe `view/usage.jsonl`; se refresca al cerrar cada sesión (hook) o a mano.
- **Recursos del equipo**: un contenedor no ve el Mac, así que `scripts/host_stats.py` (LaunchAgent `host_stats_launchagent.sh install`, cada 30 s) escribe `view/host.json`. Docker se lee del motor por el proxy de solo lectura (`/info`, `/system/df`).

## Tokens: qué se mide y qué no
1. **Observer** (`~/.cognee-plugin/observer`): todo lo que Cognee gasta al indexar. Completo.
2. **Claude Code por OpenTelemetry**: solo sesiones abiertas con `~/Documents/Developer/agents_memory_system/scripts/claude-memory <proyecto>` (variables `OTEL_*` reales; el bloque `env` de `settings.json` **no** sirve). Sugerencia: `alias cm='~/Documents/Developer/agents_memory_system/scripts/claude-memory'`.
3. **Estadísticas de sesión de Cognee**: suele ser 0 (el observer usa la suscripción).
La cuota restante de la suscripción no se puede consultar desde fuera.

## Seguridad (por diseño)
- Solo `127.0.0.1`; middleware de Host (anti DNS-rebinding), CSP estricta, `X-Frame-Options`, `no-store`.
- PostgreSQL con rol `mm_reader`: transacciones de solo lectura, límite de 15 s, una sola sentencia `SELECT/WITH/EXPLAIN/SHOW/VALUES/TABLE`.
- Docker solo vía `socket-proxy` con lista blanca (GET de logs/stats/inspect); el panel no monta el socket.
- Contenedor sin root, `cap_drop ALL`, volúmenes de datos en solo lectura.
- Todo texto dinámico se inserta con `textContent`, nunca `innerHTML`.
- `.env` (0600) no se versiona.

## Estructura
`app/` FastAPI (`main.py` endpoints; `pg.py`, `otel.py`, `observer.py`, `kb.py`, `vectors.py`, `dockerapi.py`, `storage.py`, `cognee_client.py`) · `static/` SPA sin build (vanilla JS + cytoscape vendorizado en el build) · `scripts/setup.py` · `compose.yaml` · `tests/`.

## Extenderlo
Un endpoint nuevo = una función en `app/` + una ruta en `app/main.py` + una página en `static/app.js` (`pages.<clave>`, y el menú `NAV`/`NAMES`). Mantén todo de solo lectura y los textos en lenguaje llano; añade los términos nuevos al `GLOSSARY`.

## Instalarlo en otro Mac
Lo instala el seed bundle: `agents_memory_system/seed-bundle/seed.sh panel --yes`.
