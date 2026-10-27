"use strict";
/* Management Memory — panel de control de SOLO LECTURA.
   Todo el contenido dinámico se inserta con textContent (nunca innerHTML). */

const $ = (s) => document.querySelector(s);
const SVGNS = "http://www.w3.org/2000/svg";
const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "data") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
};
const api = async (path, opts) => {
  const r = await fetch("/api" + path, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
};

/* ── formato ── */
const bytes = (n) => {
  if (n == null) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0, v = Number(n);
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v >= 100 || i === 0 ? v.toFixed(0) : v.toFixed(1)} ${u[i]}`;
};
const num = (n) => (n == null ? "—" : Number(n).toLocaleString("es-CO"));
const usd = (n) => (n == null ? "—" : `$${Number(n).toFixed(4)}`);
const ago = (iso) => {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return "hace instantes"; if (s < 5400) return `hace ${Math.round(s / 60)} min`;
  if (s < 129600) return `hace ${Math.round(s / 3600)} h`; return `hace ${Math.round(s / 86400)} d`;
};

/* ── iconos (trazo, 24×24) ── */
const ICON = {
  home: "M3 11l9-8 9 8v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z",
  book: "M4 4h12a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3zM4 17a3 3 0 0 1 3-3h12",
  cube: "M12 2l9 5v10l-9 5-9-5V7zM12 22V12M3 7l9 5 9-5",
  graph: "M6 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM18 8.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM18 20.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM8.2 10.8l7.6-3.6M8.2 13.2l7.6 3.6",
  db: "M12 8c4.4 0 8-1.3 8-3s-3.6-3-8-3-8 1.3-8 3 3.6 3 8 3zM4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-4.5-4.5",
  zap: "M13 2L4 14h7l-1 8 9-12h-7z",
  pulse: "M22 12h-4l-3 9L9 3l-3 9H2",
  sync: "M21 12a9 9 0 0 1-15.5 6.2M3 12A9 9 0 0 1 18.5 5.8M21 4v5h-5M3 20v-5h5",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01",
  check: "M20 6L9 17l-5-5",
  alert: "M12 3l10 18H2zM12 10v5M12 18h.01",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  layers: "M12 2l10 5-10 5L2 7zM2 12l10 5 10-5M2 17l10 5 10-5",
  refresh: "M21 12a9 9 0 1 1-3-6.7M21 3v6h-6",
};
const icon = (name, size = 18) => {
  const s = document.createElementNS(SVGNS, "svg");
  for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", width: size, height: size, fill: "none", stroke: "currentColor", "stroke-width": 1.8, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) s.setAttribute(k, v);
  const p = document.createElementNS(SVGNS, "path"); p.setAttribute("d", ICON[name] || ICON.info); s.append(p); return s;
};

/* ── componentes ── */
const help = (text) => h("span", { class: "help", "data-tip": text, tabindex: "0", role: "note", "aria-label": text }, "?");
const pill = (text, kind = "") => h("span", { class: `pill ${kind}` }, text);
const intro = (title, text, more) => h("div", { class: "callout" }, icon("info", 20),
  h("div", {}, h("b", {}, title), h("p", {}, text), more ? h("details", {}, h("summary", {}, "Saber más"), h("p", {}, more)) : null));
function sparkline(vals) {
  const w = 84, hgt = 30, max = Math.max(1, ...vals), min = Math.min(...vals);
  const pts = vals.map((v, i) => `${(i / (vals.length - 1)) * w},${hgt - 3 - ((v - min) / (max - min || 1)) * (hgt - 6)}`).join(" ");
  const s = document.createElementNS(SVGNS, "svg"); s.setAttribute("class", "spark"); s.setAttribute("width", w); s.setAttribute("height", hgt); s.setAttribute("viewBox", `0 0 ${w} ${hgt}`);
  const pl = document.createElementNS(SVGNS, "polyline"); pl.setAttribute("points", pts); pl.setAttribute("fill", "none"); pl.setAttribute("stroke", "var(--brand)"); pl.setAttribute("stroke-width", 2); pl.setAttribute("stroke-linecap", "round"); pl.setAttribute("stroke-linejoin", "round");
  s.append(pl); return s;
}
const kpi = ({ label, value, meta, tip, spark }) => h("div", { class: "card kpi" },
  h("div", { class: "lbl" }, label, tip ? help(tip) : null), h("div", { class: "val" }, value), meta ? h("div", { class: "meta" }, meta) : null,
  spark && spark.length > 1 ? sparkline(spark) : null);
const tile = ({ ic, name, state, tone, what, data }) => h("div", { class: `card tile ${tone}` }, h("div", { class: "ic" }, icon(ic, 20)),
  h("div", {}, h("div", { class: "name" }, name), h("div", { class: "state" }, state), h("div", { class: "what" }, what), data ? h("div", { class: "data" }, data) : null));
function table(cols, rows, opts = {}) {
  if (!rows || !rows.length) return h("div", { class: "tbl" }, h("div", { class: "empty" }, opts.empty || "Sin datos todavía."));
  return h("div", { class: "tbl" }, h("div", { class: "scroll" }, h("table", {},
    h("thead", {}, h("tr", {}, cols.map((c) => h("th", { class: c.n ? "n" : "" }, c.t, c.tip ? help(c.tip) : null)))),
    h("tbody", {}, rows.map((r) => h("tr", { class: opts.onrow ? "click" : "", onclick: opts.onrow ? (e) => opts.onrow(r, e.currentTarget) : null },
      cols.map((c) => { const v = c.f ? c.f(r) : r[c.k]; return h("td", { class: c.n ? "n" : "" }, v?.nodeType ? v : (v ?? "—")); })))))));
}
function barChart(points, { label = (p) => p.k, value = (p) => p.v, fmt = num } = {}) {
  if (!points.length) return h("div", { class: "empty" }, "Sin datos en este periodo.");
  const max = Math.max(1, ...points.map(value));
  return h("div", {}, h("div", { class: "bars" }, points.map((p) => h("div", { style: `height:${Math.max(3, (100 * value(p)) / max)}%`, data: { t: `${label(p)}: ${fmt(value(p))}` } }))),
    h("div", { class: "axis" }, h("span", {}, label(points[0])), h("span", {}, label(points[points.length - 1]))));
}
function hbars(items, fmt = num) {
  const max = Math.max(1, ...items.map((i) => i.v));
  return h("div", {}, items.map((i) => h("div", { class: "hb" }, h("span", { class: "l", title: i.l }, i.l), h("span", { class: "t" }, h("i", { style: `width:${Math.max(2, (100 * i.v) / max)}%` })), h("span", { class: "v" }, fmt(i.v)))));
}
const loading = () => h("div", { class: "empty" }, "Cargando…");
const fail = (e) => h("div", { class: "callout", style: "background:var(--bad-soft)" }, icon("alert", 20), h("div", {}, h("b", {}, "No se pudo cargar"), h("p", {}, e.message)));
async function render(fn) {
  const v = $("#view"); v.replaceChildren(loading());
  try { v.replaceChildren(await fn()); } catch (e) { v.replaceChildren(fail(e)); }
}
const section = (title, hint) => [h("h2", {}, title), hint ? h("p", { class: "hint" }, hint) : null];

/* ── lenguaje claro: nombres y explicaciones ── */
const COLLECTION = {
  DocumentChunk_text: ["Fragmentos de tus documentos", "Cada documento se corta en trozos; esta colección es la que usa la búsqueda."],
  TextSummary_text: ["Resúmenes de cada fragmento", "Un resumen corto por fragmento, generado por Claude al indexar."],
  TextDocument_name: ["Nombres de documentos", "Un vector por documento."],
  Entity_name: ["Conceptos detectados", "Módulos, reglas, decisiones… que Claude extrajo de los textos (nodos del grafo)."],
  EntityType_name: ["Categorías de conceptos", "Los tipos a los que pertenecen los conceptos (p. ej. «módulo», «regla»)."],
  EdgeType_relationship_name: ["Nombres de relaciones del grafo", "Un vector por conexión entre conceptos, aunque el nombre se repita (contiene, es_un…)."],
  SessionQAVector_text: ["Preguntas y respuestas de sesiones", "Conversaciones guardadas en el grafo."],
};
const ADVICE = {
  aristas_dominan: ["Las relaciones del grafo ocupan casi todo el espacio de vectores", "Son vectores auxiliares del grafo (el nombre de cada conexión, repetido muchas veces), no tus documentos. La búsqueda por fragmentos no los usa. Si algún día necesitas ahorrar espacio, es lo primero a mirar; hoy es solo un dato."],
  sin_ann: ["Sin índice de búsqueda rápida (ANN)", "La búsqueda compara con todos los vectores (exacta). Con cientos o miles de filas es instantánea. Solo habría que crear un índice con decenas de miles. No es un problema hoy."],
  sesiones: ["Historia de sesiones", "Cada cierre de sesión guarda un resumen con ~3 llamadas a Claude. Revisa en «Tokens y costo» si compensa lo que gastas frente a lo que te aporta."],
  vacio: ["Dataset vacío", "No contiene documentos: puedes eliminarlo sin perder nada."],
  codigo_vacio: ["Dataset de código vacío", "Lo crea el plugin aunque la indexación de código esté apagada. No consume nada."],
  no_indexados: ["Documentos pendientes de indexar", "Están en el registro pero no se confirmó su indexación. Se reintentan con el siguiente sync."],
  faltan_en_cognee: ["Documentos que desaparecieron de Cognee", "Existen en el registro pero ya no en la memoria. Hay que volver a sincronizar."],
  huerfanos: ["Documentos sin registro", "Están en Cognee pero no los gestiona el sincronizador (¿cargados a mano?)."],
  docs_pesados: ["Documentos que cuestan mucho", "Tienen muchos más fragmentos que el resto. Cada fragmento cuesta ~2 llamadas a Claude al reindexar: valora dividirlos o acortarlos."],
};
const GLOSSARY = [
  ["Memoria / base de conocimiento", "Lo que la IA «recuerda» de un proyecto: tus documentos convertidos en datos que se pueden buscar por significado."],
  ["Dataset", "Un «cajón» independiente de la memoria. Cada proyecto tiene uno de conocimiento (sus documentos) y otro de sesiones (conversaciones)."],
  ["Documento", "Un archivo de texto (normalmente Markdown) que se guardó en la memoria."],
  ["Chunk (fragmento)", "Un trozo de un documento. Se corta así para buscar con precisión y dar a Claude solo lo relevante."],
  ["Vector (embedding)", "La «huella» numérica de un texto: 768 números que representan su significado. Textos parecidos tienen huellas cercanas; así funciona la búsqueda. Se calcula en local."],
  ["Dimensión", "Cuántos números tiene cada vector (aquí 768). Más dimensiones = más detalle, más espacio."],
  ["Índice ANN", "Un atajo para buscar vectores parecidos sin compararlos con todos. Útil a partir de decenas de miles de filas."],
  ["Grafo de conocimiento", "Un mapa de conceptos (nodos) unidos por relaciones (aristas), que Claude extrae de los textos al indexar."],
  ["Nodo / Arista", "Nodo = un concepto o documento. Arista = una conexión entre dos nodos, con nombre (contiene, es_un…)."],
  ["Observer", "Un puente en tu Mac que usa tu suscripción de Claude para que Cognee pueda resumir y extraer conceptos. Cada llamada cuenta tokens."],
  ["Token", "La unidad en que se mide el texto que procesa una IA (~3-4 caracteres). Más tokens = más consumo."],
  ["Caché de tokens", "Texto que Claude ya vio y reutiliza más barato. Aparece como «lectura de caché»."],
  ["Reingesta", "Volver a indexar un documento. Cuesta unas 2 llamadas a Claude por fragmento. Sirve para estimar qué costaría reconstruir la memoria."],
  ["OpenTelemetry (OTel)", "Un estándar para medir lo que hace un programa. Claude Code lo usa para reportar cada llamada y sus tokens al collector."],
  ["Collector", "El servicio que recibe esa telemetría y la guarda en archivos que esta pantalla lee."],
  ["MCP", "El «enchufe» local por el que Claude Code consulta la memoria con herramientas (recall, remember…)."],
  ["Sesión", "Una conversación con Claude Code. Cognee puede guardar su historia para recordarla después."],
  ["Huella (espacio)", "Todo lo que ocupa un dataset: base de datos + grafo + texto crudo."],
];

/* ── páginas ── */
const pages = {};

pages.resumen = { title: "Resumen", sub: "El estado de tu memoria en un vistazo.", icon: "home", run: async () => {
  const [o, kb] = await Promise.all([api("/overview"), api("/kb")]);
  const reg = o.registry.states || {}, pending = Object.entries(reg).filter(([k]) => k !== "indexed").reduce((s, [, v]) => s + v, 0);
  const issues = [];
  [["Cognee (API)", o.cognee], ["MCP", o.mcp], ["PostgreSQL", o.postgres], ["Observer", o.observer]].forEach(([n, s]) => { if (!s.ok) issues.push(`${n} no responde.`); });
  if (!o.collector.ok) issues.push("El collector de telemetría no tiene archivos.");
  if (pending) issues.push(`${pending} documento(s) sin indexar correctamente (ver «Sincronización»).`);
  kb.datasets.forEach((d) => d.flags.filter((f) => f.level === "warn").forEach((f) => issues.push(`${d.name}: ${f.text}`)));
  const root = h("div", {});
  root.append(issues.length
    ? h("div", { class: "attention warn" }, icon("alert", 22), h("div", {}, h("h2", {}, `${issues.length} ${issues.length === 1 ? "cosa requiere" : "cosas requieren"} tu atención`), h("ul", {}, issues.map((i) => h("li", {}, i)))))
    : h("div", { class: "attention ok" }, icon("check", 22), h("div", {}, h("h2", {}, "Todo en orden"), h("span", { class: "muted" }, "Los servicios responden, todos los documentos están indexados y no hay avisos."))));
  const t = (ok, ic, name, what, data) => tile({ ic, name, tone: ok ? "ok" : "bad", state: ok ? "Funcionando" : "No responde", what, data });
  root.append(...section("Salud de los servicios", "Cada pieza del sistema y para qué sirve. Todo corre en tu Mac."));
  root.append(h("div", { class: "grid" },
    t(o.cognee.ok, "layers", "Cognee", "El servicio local que guarda y busca la memoria.", o.cognee.version && `Versión ${o.cognee.version}`),
    t(o.postgres.ok, "db", "Base de datos", "Donde viven los vectores y los datos.", o.postgres.ok && `${bytes(o.postgres.size_bytes)} · ${o.postgres.connections} conexiones`),
    t(o.observer.ok, "zap", "Observer (Claude)", "Permite a Cognee usar tu suscripción de Claude al indexar.", o.observer.ok && `${num(o.observer.calls)} llamadas desde que arrancó`),
    t(o.mcp.ok, "search", "MCP", "Por donde Claude Code consulta la memoria (local).", "Puerto 45873"),
    t(o.collector.ok, "pulse", "Telemetría (OTel)", "Recoge cuántos tokens gasta Claude Code.", `${o.collector.files} archivo(s) · ${bytes(o.collector.bytes)} · ${ago(o.collector.latest_file)}`),
    t(pending === 0, "sync", "Sincronización", "Mantiene la memoria igual a tus documentos.", `${reg.indexed || 0} de ${o.registry.total} indexados`)));
  const obs = o.observer_usage, ot = o.otel_usage.total;
  root.append(...section("Cuánta memoria hay y qué cuesta", "Pasa el cursor sobre «?» para ver qué significa cada número."));
  const totalFoot = kb.datasets.reduce((s, d) => s + (d.footprint_bytes || 0), 0), docs = kb.datasets.reduce((s, d) => s + (d.documents || 0), 0), vec = kb.datasets.reduce((s, d) => s + (d.vector_rows || 0), 0);
  root.append(h("div", { class: "grid" },
    kpi({ label: "Espacio total", value: bytes(totalFoot), meta: `${kb.projects.length} proyecto(s) · ${kb.datasets.length} datasets`, tip: "Todo lo que ocupa la memoria: base de datos + grafo + texto." }),
    kpi({ label: "Documentos", value: num(docs), meta: `${num(kb.datasets.reduce((s, d) => s + d.chunks, 0))} fragmentos`, tip: "Archivos guardados y los trozos en que se cortaron para buscar." }),
    kpi({ label: "Vectores", value: num(vec), meta: "768 números cada uno", tip: "La huella numérica de cada texto, concepto y relación. Se calcula en local y permite buscar por significado." }),
    kpi({ label: "Llamadas a Claude", value: num(obs.total.calls), meta: `${num(obs.total.tokens)} tokens`, tip: "Veces que Cognee usó tu suscripción para indexar. Se miden en el observer.", spark: obs.by_day.map((d) => d.calls) }),
    kpi({ label: "Sesiones medidas", value: num(ot.sessions), meta: `${num(ot.total)} tokens`, tip: "Sesiones de Claude Code con telemetría activada. Solo cuentan las lanzadas con «claude-memory».", spark: o.otel_usage.by_day.map((d) => d.total) })));
  root.append(h("div", { class: "grid two", style: "margin-top:14px" },
    h("div", { class: "card" }, h("h3", {}, "Llamadas a Claude por día"), barChart(obs.by_day, { label: (p) => p.day, value: (p) => p.calls }), h("p", { class: "hint small" }, "Cada barra es un día. Cada llamada es un paso de indexación o de resumen.")),
    h("div", { class: "card" }, h("h3", {}, "Qué ocupa más espacio"), hbars(kb.datasets.filter((d) => d.footprint_bytes).sort((a, b) => b.footprint_bytes - a.footprint_bytes).map((d) => ({ l: d.name, v: d.footprint_bytes })), bytes), h("p", { class: "hint small" }, "Por dataset. Entra en «Bases de conocimiento» para ver el desglose."))));
  return root;
} };

pages.conocimiento = { title: "Bases de conocimiento", sub: "Cuánta memoria tiene cada proyecto, cuánto pesa y qué cuesta rehacerla.", icon: "book", run: async () => {
  const o = await api("/kb");
  const root = h("div", {});
  root.append(intro("¿Qué estoy viendo?", "Cada proyecto tiene su propia base de conocimiento: sus documentos convertidos en datos que la IA puede consultar. Aquí ves cuánta hay, cuánto espacio ocupa y cuánto costaría reconstruirla, para decidir si conviene compactar o eliminar algo.",
    "«Reconstruir» es el costo de volver a indexar todo: ~2 llamadas a Claude por fragmento. Se calcula con el promedio real que mide el observer."));
  const totalFoot = o.datasets.reduce((s, d) => s + (d.footprint_bytes || 0), 0), reingest = o.projects.reduce((s, p) => s + p.est_reingest_tokens, 0);
  root.append(h("div", { class: "grid" },
    kpi({ label: "Proyectos con memoria", value: num(o.projects.length), meta: o.projects.map((p) => p.project).join(", ") }),
    kpi({ label: "Espacio total", value: bytes(totalFoot), meta: `Base de datos ${bytes(o.pg.size_bytes)} · grafo y archivos ${bytes(o.storage.total_bytes)}`, tip: "Lo que ocupa todo en disco." }),
    kpi({ label: "Costo de reconstruir todo", value: `${num(reingest)} tokens`, meta: `≈ ${num(o.avg_tokens_per_call)} por llamada`, tip: "Estimación: fragmentos × 2 llamadas × tokens medios por llamada." })));
  root.append(...section("Por proyecto", "Los datasets de un mismo proyecto (conocimiento, sesiones, código) se suman."));
  root.append(table([
    { t: "Proyecto", f: (r) => h("strong", {}, r.project) }, { t: "Contiene", f: (r) => r.datasets.map((d) => d.kind).join(" · ") },
    { t: "Documentos", n: 1, f: (r) => num(r.documents) }, { t: "Fragmentos", n: 1, f: (r) => num(r.chunks), tip: "Trozos en que se cortan los documentos." }, { t: "Vectores", n: 1, f: (r) => num(r.vector_rows) },
    { t: "Espacio", n: 1, f: (r) => bytes(r.footprint_bytes) }, { t: "Reconstruir", n: 1, f: (r) => `${num(r.est_reingest_tokens)} tok`, tip: "Tokens que costaría volver a indexarlo." }], o.projects));
  root.append(...section("Por dataset", "Haz clic en una fila para ver el detalle, los documentos que más cuestan y qué hacer."));
  const box = h("div", {});
  root.append(table([
    { t: "Dataset", f: (r) => h("span", {}, h("strong", {}, r.name), " ", pill(r.kind, "brand")) }, { t: "Docs", n: 1, f: (r) => num(r.documents) },
    { t: "Texto", n: 1, f: (r) => `${num(r.est_tokens)} tok`, tip: "Tamaño del texto original, en tokens aproximados." }, { t: "Conceptos", n: 1, f: (r) => num(r.nodes), tip: "Nodos del grafo." }, { t: "Conexiones", n: 1, f: (r) => num(r.edges), tip: "Aristas del grafo." },
    { t: "Vectores", n: 1, f: (r) => num(r.vector_rows) }, { t: "Espacio", n: 1, f: (r) => bytes(r.footprint_bytes) },
    { t: "Avisos", f: (r) => { const n = r.flags.filter((f) => f.level !== "info").length; return n ? pill(`${n} ${n === 1 ? "aviso" : "avisos"}`, "warn") : pill("sin avisos", "ok"); } }],
    o.datasets, { onrow: (r, tr) => { document.querySelectorAll("tr.sel").forEach((x) => x.classList.remove("sel")); tr.classList.add("sel"); detail(r.id, box); } }));
  root.append(box);
  return root;
} };
async function detail(id, box) {
  box.replaceChildren(loading());
  try {
    const d = await api(`/kb/${id}`);
    box.replaceChildren(...section(`Detalle de ${d.name}`, null),
      h("div", { class: "grid" }, kpi({ label: "Documentos", value: num(d.documents), meta: `${bytes(d.raw_bytes)} de texto` }), kpi({ label: "Fragmentos", value: num(d.chunks), meta: `≈ ${num(d.est_tokens)} tokens` }),
        kpi({ label: "Reconstruir", value: `${num(d.est_reingest_calls)} llamadas`, meta: `≈ ${num(d.est_reingest_tokens)} tokens`, tip: "Fragmentos × 2 llamadas a Claude." }),
        kpi({ label: "Espacio", value: bytes(d.footprint_bytes), meta: `Postgres ${bytes(d.pg_bytes)} · grafo ${bytes(d.graph_bytes)}` })),
      ...section("Qué significa y qué puedes hacer", "Avisos y datos que ayudan a decidir si compactar o limpiar."),
      ...(d.flags.length ? d.flags.map((f) => { const a = ADVICE[f.code]; return h("div", { class: `advice ${f.level}` }, icon(f.level === "warn" ? "alert" : "info", 18), h("div", {}, h("b", {}, a ? a[0] : f.code), h("span", {}, a ? a[1] : f.text), a ? h("div", { class: "small muted", style: "margin-top:4px" }, "Dato: " + f.text) : null)); }) : [h("div", { class: "empty" }, "Sin avisos para este dataset.")]),
      ...section("Documentos, del que más cuesta al que menos", "Los fragmentos determinan el costo de reindexar. Un documento con muchos fragmentos es candidato a dividirse o acortarse."),
      table([{ t: "Documento", f: (r) => r.path || r.name }, { t: "Estado", f: (r) => (r.status ? pill(r.status === "indexed" ? "indexado" : r.status, r.status === "indexed" ? "ok" : "warn") : pill("sin registro", "warn")) },
        { t: "Fragmentos", n: 1, f: (r) => num(r.chunks) }, { t: "Texto", n: 1, f: (r) => `${num(r.est_tokens)} tok` }, { t: "Reindexar", n: 1, f: (r) => `${num(r.est_reingest_tokens)} tok` }, { t: "Actualizado", f: (r) => ago(r.updated || r.created) }], d.docs),
      ...section("Dónde están los vectores", "Una colección por tipo de texto, guardada en la base de datos para buscar por significado."), vectorTable(d.collections));
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) { box.replaceChildren(fail(e)); }
}
function vectorTable(cols) {
  return table([
    { t: "Qué guarda", f: (r) => { const c = COLLECTION[r.table]; return h("div", {}, h("strong", {}, c ? c[0] : r.table), c ? h("div", { class: "muted small" }, c[1]) : null, h("code", {}, r.table)); } },
    { t: "Vectores", n: 1, f: (r) => num(r.rows) }, { t: "Dimensión", n: 1, f: (r) => r.dim, tip: "Cuántos números tiene cada vector." },
    { t: "Espacio", n: 1, f: (r) => bytes(r.bytes_total) }, { t: "Índice rápido", f: (r) => (r.has_ann_index ? pill("sí", "ok") : pill("no (búsqueda exacta)")), tip: "Atajo de búsqueda (ANN). Sin él compara contra todos: perfecto para pocos datos." },
    { t: "Ejemplo", f: (r) => (r.sample ? h("div", {}, h("div", { class: "mono muted" }, `[${r.sample.first_components.slice(0, 4).join(", ")} …]`), h("div", { class: "small" }, r.sample.item.slice(0, 60))) : "—") }], cols);
}

pages.vectores = { title: "Vectores", sub: "Qué huellas numéricas se crean, dónde se guardan y cuánto pesan.", icon: "cube", run: async () => {
  const all = await api("/vectors");
  const root = h("div", {});
  root.append(intro("¿Qué es un vector y dónde se crea?", "Para buscar por significado (no por palabras exactas), cada texto se convierte en una lista de 768 números: su «huella». Dos textos con significado parecido tienen huellas cercanas. Se calculan dentro de tu Mac, en el contenedor de Cognee, y se guardan en PostgreSQL (un esquema por dataset).",
    "El modelo es jina-embeddings-v2-base-es: se descargó una vez, corre en local, no usa tu suscripción ni internet, y entiende español e inglés."));
  for (const d of all) root.append(...section(d.dataset, `${num(d.rows)} vectores · ${bytes(d.bytes)} en disco · esquema ${d.schema}`), d.collections.length ? vectorTable(d.collections) : h("div", { class: "empty" }, "Este dataset no tiene vectores."));
  return root;
} };

const TYPE_COLORS = { Entity: "#0e7c86", EntityType: "#c2650c", DocumentChunk: "#4f7cc4", TextSummary: "#8a63b5", TextDocument: "#12805c", Timestamp: "#98a2b3", default: "#667085" };
const TYPE_NAMES = { Entity: "Conceptos", EntityType: "Categorías", DocumentChunk: "Fragmentos", TextSummary: "Resúmenes", TextDocument: "Documentos", Timestamp: "Fechas" };
pages.grafo = { title: "Grafo", sub: "El mapa de conceptos que Claude extrajo de tus documentos.", icon: "graph", run: async () => {
  const ds = (await api("/datasets")).filter((d) => d.nodes);
  if (!ds.length) return h("div", {}, intro("Aún no hay grafo", "Cuando se indexen documentos, aquí aparecerá el mapa de conceptos."));
  const sel = h("select", {}, ds.map((d) => h("option", { value: d.id }, `${d.name} (${num(d.nodes)} nodos)`)));
  const max = h("input", { type: "number", value: 300, min: 20, max: 3000, style: "width:90px" });
  const chips = h("div", { class: "row" }), info = h("p", { class: "hint" });
  const panel = h("div", { class: "card" }, h("h3", {}, "Detalle"), h("p", { class: "muted" }, "Haz clic en un punto para ver qué es y sus propiedades."));
  const cyBox = h("div", { id: "cy" }); let cy = null, stats = null; const active = new Set();
  const load = async () => {
    info.textContent = "Cargando grafo…";
    try {
      const types = active.size ? [...active].join(",") : "";
      const g = await api(`/datasets/${sel.value}/graph?max_nodes=${max.value}&types=${encodeURIComponent(types)}`);
      if (!stats) { stats = g.stats; chips.replaceChildren(...Object.entries(stats.types).map(([t, c]) => { active.add(t); return h("span", { class: "pill chip", style: `box-shadow:inset 0 0 0 2px ${TYPE_COLORS[t] || TYPE_COLORS.default}`, title: "Mostrar/ocultar", onclick: (e) => { active.has(t) ? active.delete(t) : active.add(t); e.currentTarget.classList.toggle("off"); load(); } }, `${TYPE_NAMES[t] || t} · ${c}`); })); }
      info.textContent = `Mostrando ${g.stats.shown_nodes} de ${g.stats.nodes} puntos y ${g.stats.shown_edges} de ${g.stats.edges} conexiones${g.stats.truncated ? " (los más conectados)" : ""}.`;
      if (cy) cy.destroy();
      cy = cytoscape({ container: cyBox, elements: [...g.nodes.map((n) => ({ data: { id: n.id, label: n.label, type: n.type, degree: n.degree, props: n.props } })), ...g.edges.map((e, i) => ({ data: { id: "e" + i, source: e.source, target: e.target, label: e.label } }))],
        style: [{ selector: "node", style: { "background-color": (n) => TYPE_COLORS[n.data("type")] || TYPE_COLORS.default, label: "data(label)", "font-size": 9, color: "#667085", "min-zoomed-font-size": 10, "text-wrap": "ellipsis", "text-max-width": 90, width: "mapData(degree,0,40,8,34)", height: "mapData(degree,0,40,8,34)" } },
          { selector: "edge", style: { width: 0.6, "line-color": "#b8c0cc", "curve-style": "haystack", opacity: 0.5 } }, { selector: "node:selected", style: { "border-width": 3, "border-color": "#c2650c" } }],
        layout: { name: "cose", animate: false, nodeRepulsion: 9000, idealEdgeLength: 60 } });
      cy.on("tap", "node", (ev) => { const n = ev.target.data(); panel.replaceChildren(h("h3", {}, TYPE_NAMES[n.type] || n.type), h("strong", {}, n.label), h("p", { class: "muted" }, `${n.degree} conexiones`), h("pre", {}, JSON.stringify(n.props, null, 2))); });
    } catch (e) { info.textContent = ""; cyBox.replaceChildren(fail(e)); }
  };
  sel.onchange = () => { stats = null; active.clear(); load(); }; max.onchange = load;
  setTimeout(async () => { await load(); if (stats) $("#rels").replaceChildren(hbars(Object.entries(stats.relations).sort((a, b) => b[1] - a[1]).map(([l, v]) => ({ l, v })))); }, 0);
  return h("div", {}, intro("¿Qué es el grafo?", "Al indexar un documento, Claude identifica los conceptos que aparecen (módulos, reglas, decisiones…) y cómo se relacionan. Cada punto es un concepto, fragmento o documento; cada línea es una relación con nombre. Los puntos grandes son los más conectados."),
    h("div", { class: "row" }, sel, h("span", { class: "muted" }, "máx. puntos"), max, h("button", { onclick: load }, "Cargar")), h("div", { style: "margin:10px 0" }, chips), info,
    h("div", { class: "split" }, cyBox, panel), ...section("Tipos de relación", "Cuántas conexiones hay de cada clase."), h("div", { class: "card", id: "rels" }));
} };

pages.postgres = { title: "PostgreSQL", sub: "Explora la base de datos donde viven los vectores (solo lectura).", icon: "db", run: async () => {
  const schemas = await api("/pg/schemas");
  const right = h("div", {}, h("div", { class: "empty" }, "Elige un esquema a la izquierda para ver sus tablas."));
  const showTable = async (schema, tbl, offset = 0) => {
    right.replaceChildren(loading());
    try {
      const d = await api(`/pg/table?schema=${encodeURIComponent(schema)}&table=${encodeURIComponent(tbl)}&limit=25&offset=${offset}`);
      right.replaceChildren(...section(`${tbl}`, schema), table([{ t: "Columna", k: "name" }, { t: "Tipo", k: "type" }, { t: "Admite vacío", f: (c) => (c.nullable ? "sí" : "no") }], d.columns),
        ...section(`Filas ${offset + 1}–${offset + d.rows.length}`, "Los vectores y los textos largos se muestran resumidos."), table(d.columns.map((c, i) => ({ t: c.name, f: (r) => h("span", { class: "mono" }, String(r[i] ?? "NULL")) })), d.rows),
        h("div", { class: "row", style: "margin-top:10px" }, offset ? h("button", { class: "ghost", onclick: () => showTable(schema, tbl, Math.max(0, offset - 25)) }, "← Anterior") : null, d.rows.length === 25 ? h("button", { class: "ghost", onclick: () => showTable(schema, tbl, offset + 25) }, "Siguiente →") : null));
    } catch (e) { right.replaceChildren(fail(e)); }
  };
  const showSchema = async (s) => {
    right.replaceChildren(loading());
    try {
      const t = await api(`/pg/tables?schema=${encodeURIComponent(s.schema)}`);
      right.replaceChildren(...section(s.dataset ? `Dataset ${s.dataset}` : `Esquema ${s.schema}`, s.schema), table([{ t: "Tabla", f: (r) => h("code", {}, r.table) }, { t: "Filas", n: 1, f: (r) => num(r.rows) }, { t: "Espacio", n: 1, f: (r) => bytes(r.bytes) }], t, { onrow: (r) => showTable(s.schema, r.table) }));
    } catch (e) { right.replaceChildren(fail(e)); }
  };
  const left = table([{ t: "Esquema", f: (s) => h("div", {}, h("strong", {}, s.dataset || s.schema), s.dataset ? h("div", { class: "muted small mono" }, s.schema.slice(0, 18) + "…") : null) }, { t: "Tablas", n: 1, k: "tables" }, { t: "Espacio", n: 1, f: (s) => bytes(s.bytes) }], schemas, { onrow: showSchema });
  const sql = h("textarea", {}, "select count(*) as fragmentos from \"ds_3efa20ebbd3554f9b57a4368b6ec1da0\".\"DocumentChunk_text\""), out = h("div", {});
  const run = async () => {
    out.replaceChildren(loading());
    try {
      const r = await api("/pg/query", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sql: sql.value }) });
      out.replaceChildren(table(r.columns.map((c, i) => ({ t: c, f: (row) => h("span", { class: "mono" }, String(row[i] ?? "NULL")) })), r.rows), r.truncated ? h("p", { class: "hint" }, "Resultado recortado a 500 filas.") : null);
    } catch (e) { out.replaceChildren(fail(e)); }
  };
  return h("div", {}, intro("¿Qué es esto?", "PostgreSQL es la base de datos donde Cognee guarda los vectores. Cada dataset tiene su propio esquema (ds_…) con una tabla por tipo de texto. Esta vista es de solo lectura: no puedes cambiar nada desde aquí, ni siquiera con la consola SQL.", "La conexión usa un rol propio (mm_reader) con permisos de solo lectura, transacciones de lectura y un límite de 15 segundos por consulta."),
    h("div", { class: "split", style: "grid-template-columns:380px minmax(0,1fr)" }, left, right), ...section("Consola SQL", "Una sola consulta de lectura (SELECT, WITH, EXPLAIN, SHOW)."), sql, h("div", { class: "row", style: "margin:10px 0" }, h("button", { onclick: run }, "Ejecutar")), out);
} };

pages.busqueda = { title: "Búsqueda", sub: "Prueba cómo recupera la memoria lo que le preguntas.", icon: "search", run: async () => {
  const ds = await api("/datasets");
  const sel = h("select", {}, ds.filter((d) => d.documents).map((d) => h("option", { value: d.name }, d.name)));
  const q = h("input", { placeholder: "Escribe una pregunta, p. ej. «¿qué umbrales usa la calificación?»", style: "flex:1;min-width:300px" }), k = h("input", { type: "number", value: 5, min: 1, max: 20, style: "width:70px" });
  const out = h("div", {});
  const go = async () => {
    if (!q.value.trim()) return; out.replaceChildren(loading()); const t0 = performance.now();
    try {
      const r = await api("/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dataset: sel.value, query: q.value, top_k: Number(k.value) }) });
      out.replaceChildren(h("p", { class: "hint" }, `${r.results.length} resultados en ${Math.round(performance.now() - t0)} ms · sin llamadas a Claude · distancia menor = más parecido`),
        ...r.results.map((x, i) => h("div", { class: "card", style: "margin:10px 0" }, h("div", { class: "row" }, pill(`#${i + 1}`, "brand"), h("strong", {}, x.path || x.document_id || "?"), h("span", { class: "spacer" }), pill(`distancia ${x.score?.toFixed?.(3) ?? x.score}`), x.status ? pill(x.status === "indexed" ? "indexado" : x.status, x.status === "indexed" ? "ok" : "warn") : null), h("p", { style: "white-space:pre-wrap;margin:10px 0 0" }, (x.text || "").slice(0, 900)))));
    } catch (e) { out.replaceChildren(fail(e)); }
  };
  q.addEventListener("keydown", (e) => e.key === "Enter" && go());
  return h("div", {}, intro("¿Para qué sirve?", "Es el mismo mecanismo que usa Claude cuando consulta la memoria. Escribes una pregunta, se convierte en un vector (en local) y se devuelven los fragmentos más cercanos. Sirve para comprobar si la memoria «entiende» lo que le preguntas. No gasta tokens de tu suscripción.", "Usa el modo CHUNKS (fragmentos): es el más barato, sin llamadas a Claude."),
    h("div", { class: "row" }, sel, q, h("span", { class: "muted" }, "resultados"), k, h("button", { onclick: go }, "Buscar")), out);
} };

pages.tokens = { title: "Tokens y costo", sub: "Cuánto texto procesa la IA y de dónde sale ese consumo.", icon: "zap", run: async () => {
  const [t, otel] = await Promise.all([api("/tokens?days=30"), api("/otel")]);
  const root = h("div", {});
  const o = t.observer.total || {}, c = t.claude_code.total, s = t.cognee_sessions.stats || {};
  root.append(intro("¿Qué es un token y qué mide esta pantalla?", "Un token es la unidad con que se mide el texto que procesa una IA (~3-4 caracteres). Aquí se cuentan tokens, no dinero: tu suscripción de Claude no cobra por token y su cuota restante no se puede consultar desde fuera. Hay tres fuentes distintas, cada una mide algo diferente.",
    "Para que una sesión de Claude Code aparezca en la fuente 2, hay que abrirla con «scripts/claude-memory <proyecto>» (o definir las variables OTEL_* en la terminal). El bloque «env» de los ajustes del proyecto no sirve para esto. Las sesiones normales no se miden."));
  root.append(...section("1 · Lo que Cognee gasta en indexar (el observer)", "Cada vez que Cognee resume o extrae conceptos, llama a Claude a través del observer. Esta fuente es completa: no se le escapa ninguna llamada."));
  root.append(h("div", { class: "grid" }, kpi({ label: "Llamadas", value: num(o.calls), spark: t.observer.by_day.map((d) => d.calls) }), kpi({ label: "Tokens", value: num(o.tokens), meta: `${num(o.avg_tokens)} por llamada`, spark: t.observer.by_day.map((d) => d.tokens) }),
    kpi({ label: "Rapidez (mediana)", value: `${num(o.p50_ms)} ms`, meta: `p95: ${num(o.p95_ms)} ms`, tip: "p95: el 95 % de las llamadas tarda menos que esto." })));
  root.append(h("div", { class: "grid two", style: "margin-top:14px" }, h("div", { class: "card" }, h("h3", {}, "Tokens por día"), barChart(t.observer.by_day, { label: (p) => p.day, value: (p) => p.tokens })),
    h("div", { class: "card" }, h("h3", {}, "Últimas llamadas"), table([{ t: "Hora", f: (r) => (r.ts || "").slice(5, 16).replace("T", " ") }, { t: "Tokens", n: 1, f: (r) => num(r.tokens) }, { t: "Duración", n: 1, f: (r) => `${num(r.duration_ms)} ms` }], (t.observer.recent || []).slice(0, 8)))));
  root.append(...section("2 · Lo que gasta Claude Code (telemetría)", "Cada respuesta de Claude en las sesiones medidas: tokens de entrada, de salida y de caché. El costo es el equivalente en API, no lo que cobra tu suscripción."));
  root.append(h("div", { class: "grid" }, kpi({ label: "Llamadas", value: num(c.calls), meta: `${c.sessions} sesiones` }), kpi({ label: "Tokens totales", value: num(c.total), meta: `entrada ${num(c.input)} · salida ${num(c.output)}` }),
    kpi({ label: "Caché", value: num(c.cache_read), meta: `escritura ${num(c.cache_creation)}`, tip: "Texto que Claude ya había visto y reutiliza más barato." }), kpi({ label: "Costo equivalente en API", value: usd(c.cost), tip: "Referencia: cuánto costaría si pagaras por uso en lugar de suscripción." })));
  root.append(h("h3", { style: "margin-top:18px" }, "Por corrida"), table([{ t: "Proyecto", f: (r) => r.project || "—" }, { t: "Corrida", f: (r) => r.run || "(sin run_id)" }, { t: "Var.", f: (r) => r.variant || "—", tip: "A = sin memoria, B = con memoria (comparaciones)." }, { t: "Llamadas", n: 1, k: "calls" }, { t: "Tokens", n: 1, f: (r) => num(r.total) }, { t: "Costo", n: 1, f: (r) => usd(r.cost) }, { t: "Mediana", n: 1, f: (r) => `${num(r.p50_ms)} ms` }], t.claude_code.by_run));
  root.append(h("h3", { style: "margin-top:18px" }, "Por modelo"), table([{ t: "Modelo", k: "model" }, { t: "Llamadas", n: 1, k: "calls" }, { t: "Tokens", n: 1, f: (r) => num(r.total) }, { t: "Costo", n: 1, f: (r) => usd(r.cost) }], t.claude_code.by_model));
  root.append(...section("3 · Lo que Cognee registra por sesión", "Las sesiones guardadas en el servidor. Suele estar a cero porque el observer usa la suscripción."));
  root.append(h("div", { class: "grid" }, kpi({ label: "Sesiones (30 días)", value: num(s.sessions), meta: `${s.abandoned ?? 0} abandonadas` }), kpi({ label: "Tokens", value: num(s.tokens_total), meta: `entrada ${num(s.tokens_in)} · salida ${num(s.tokens_out)}` }), kpi({ label: "Gasto registrado", value: usd(s.total_spend_usd) })));
  root.append(...section("Salud de la medición", "Comprobaciones para saber si los números son fiables."));
  root.append(h("div", { class: "grid two" }, h("div", {}, h("h3", {}, "Eventos recibidos"), table([{ t: "Evento", f: (r) => h("code", {}, r.name) }, { t: "Cantidad", n: 1, f: (r) => num(r.count) }], otel.events)),
    h("div", {}, h("h3", {}, "Conciliación: logs vs. métricas"), table([{ t: "Corrida", f: (r) => r.run }, { t: "Tipo", k: "kind" }, { t: "Logs", n: 1, f: (r) => num(r.logs) }, { t: "Métricas", n: 1, f: (r) => num(r.metrics) }, { t: "Dif.", n: 1, f: (r) => (r.diff_pct == null ? "—" : `${r.diff_pct}%`), tip: "Las métricas suelen quedarse cortas en sesiones breves; los logs son la fuente fiable." }], otel.reconciliation))));
  return root;
} };

pages.llamadas = { title: "API y contenedores", sub: "Quién habla con Cognee, con qué frecuencia y si los servicios están sanos.", icon: "pulse", run: async () => {
  const hours = h("select", {}, [1, 6, 24, 72, 168].map((x) => h("option", { value: x, selected: x === 24 }, `últimas ${x} h`)));
  const body = h("div", {});
  const load = async () => {
    body.replaceChildren(loading());
    try {
      const [c, a] = await Promise.all([api("/containers"), api(`/api-calls?hours=${hours.value}`)]);
      const parts = [...section("Contenedores", "Los programas que forman el sistema. Si alguno se reinicia mucho o se queda sin memoria, aparecerá aquí.")];
      parts.push(c.available ? table([{ t: "Servicio", f: (r) => h("strong", {}, r.service) },
        { t: "Estado", f: (r) => (r.state === "exited" && r.exit_code === 0 ? pill("completado", "ok") : pill(`${r.state === "running" ? "activo" : r.state}${r.health ? " · " + r.health : ""}`, r.state === "running" && r.health !== "unhealthy" ? "ok" : "bad")) },
        { t: "CPU", n: 1, f: (r) => (r.cpu_pct == null ? "—" : `${r.cpu_pct}%`) }, { t: "Memoria", n: 1, f: (r) => (r.mem_bytes == null ? "—" : bytes(r.mem_bytes)) }, { t: "Reinicios", n: 1, k: "restarts", tip: "Veces que Docker lo reinició por un fallo." }, { t: "Activo desde", f: (r) => ago(r.started) }], c.containers)
        : h("div", { class: "empty" }, "Sin acceso a Docker (proxy no configurado)."));
      if (a.available === false || a.ok === false) parts.push(...section("Llamadas a la API"), h("div", { class: "empty" }, a.error || "Docker no disponible."));
      else {
        parts.push(...section(`Llamadas a la API de Cognee · ${num(a.total)} en ${a.hours} h`, a.note),
          h("div", { class: "grid" }, kpi({ label: "Llamadas", value: num(a.total), meta: `${num(a.health_checks)} chequeos de salud aparte` }), kpi({ label: "Errores", value: num((a.status["4xx"] || 0) + (a.status["5xx"] || 0)), meta: "respuestas 4xx/5xx", tip: "Un 404 suele ser un dataset inexistente; un 5xx, un fallo del servidor." }), ...a.callers.slice(0, 3).map((x) => kpi({ label: "Origen", value: num(x.count), meta: x.caller }))),
          h("div", { class: "card", style: "margin:14px 0" }, h("h3", {}, "Llamadas por hora"), barChart(a.per_hour, { label: (p) => p.hour.replace("T", " "), value: (p) => p.count })),
          h("h3", {}, "Por endpoint"), table([{ t: "Qué hace", f: (r) => h("code", {}, `${r.method} ${r.path}`) }, { t: "Llamadas", n: 1, f: (r) => num(r.count) }, { t: "Errores", n: 1, f: (r) => (r.errors ? pill(r.errors, "bad") : "0") },
            { t: "¿Gasta tokens?", f: (r) => (r.llm ? pill("puede usar Claude", "warn") : "no"), tip: "Los endpoints cognify, improve, remember y memify llaman a Claude." }, { t: "Quién llama", f: (r) => Object.entries(r.callers).map(([k, v]) => `${k} (${v})`).join(", ") }], a.endpoints));
      }
      body.replaceChildren(...parts);
    } catch (e) { body.replaceChildren(fail(e)); }
  };
  hours.onchange = load; setTimeout(load, 0);
  return h("div", {}, intro("¿Qué estoy viendo?", "Cada vez que un programa usa la memoria (los hooks de Claude Code, el MCP, tus scripts) hace una llamada a la API de Cognee, que corre en tu Mac. Aquí se cuentan, se agrupan por endpoint y se muestra quién las hizo. Sirve para detectar llamadas de más, errores y consumo anormal."), h("div", { class: "row" }, h("span", { class: "muted" }, "Periodo"), hours), body);
} };

pages.sync = { title: "Sincronización", sub: "Qué documentos están indexados y cuál fue su último estado.", icon: "sync", run: async () => {
  const rows = await api("/registry");
  const bad = rows.filter((r) => r.status !== "indexed").length;
  return h("div", {}, intro("¿Qué es la sincronización?", "Tus documentos Markdown son la fuente de verdad. La sincronización los copia a la memoria solo cuando cambian (comparando un «hash», la huella del archivo) y comprueba que se pueden recuperar antes de marcarlos como indexados.", "Se lanza a mano con «memctl.sh sync <repo> --apply», una vez por hito de trabajo, no tras cada edición."),
    h("div", { class: "grid" }, kpi({ label: "Documentos registrados", value: num(rows.length) }), kpi({ label: "Indexados", value: num(rows.length - bad), meta: bad ? `${bad} pendientes` : "todos" })),
    ...section("Registro", "Un documento aparece «indexado» solo si una búsqueda lo recuperó."), table([{ t: "Proyecto", k: "project" }, { t: "Documento", k: "path" }, { t: "Estado", f: (r) => pill(r.status === "indexed" ? "indexado" : r.status, r.status === "indexed" ? "ok" : "warn") }, { t: "Hash", f: (r) => h("code", {}, r.hash), tip: "Huella del archivo: si cambia, se reindexa." }, { t: "Commit", k: "commit" }, { t: "Actualizado", f: (r) => ago(r.updated) }, { t: "Error", f: (r) => r.last_error || "—" }], rows));
} };

pages.guia = { title: "Guía y glosario", sub: "Todo lo que necesitas para leer este panel.", icon: "info", run: async () => h("div", {},
  intro("¿Qué es Management Memory?", "Un panel de control, de solo lectura, para entender y vigilar la memoria que usa tu IA: cuánto conocimiento hay por proyecto, qué espacio ocupa, qué cuesta mantenerla y si todo funciona. No modifica nada: sirve para tomar decisiones."),
  ...section("¿Qué es local y qué sale de tu Mac?", "Todo corre en tu Mac. Solo un paso usa un servicio externo."),
  h("div", { class: "grid two" }, h("div", { class: "card" }, h("h3", {}, "Local (no sale de tu Mac)"), h("ul", {}, h("li", {}, "Cognee, la base de datos, el MCP y este panel."), h("li", {}, "Crear los vectores (embeddings): lo hace un modelo local."), h("li", {}, "Buscar: tu pregunta se convierte en vector y se compara en PostgreSQL."))),
    h("div", { class: "card" }, h("h3", {}, "Sale a Claude (Anthropic)"), h("ul", {}, h("li", {}, "Al indexar: los fragmentos se envían a Claude (vía el observer) para resumirlos y extraer conceptos. Gasta tokens."), h("li", {}, "Al preguntar: el texto recuperado se incluye en tu conversación con Claude Code.")))),
  ...section("Cómo se conecta todo", "De tu documento a una respuesta."), h("div", { class: "card" }, h("ol", { class: "steps" },
    h("li", {}, h("b", {}, "Escribes un documento "), "(Markdown) en tu proyecto."),
    h("li", {}, h("b", {}, "La sincronización lo envía a Cognee "), "solo si cambió."),
    h("li", {}, h("b", {}, "Cognee lo corta en fragmentos, "), "calcula sus vectores en local y pide a Claude (vía el observer) resúmenes y conceptos: aquí se gastan tokens."),
    h("li", {}, h("b", {}, "Se guardan los vectores "), "en PostgreSQL y el grafo en su propio archivo."),
    h("li", {}, h("b", {}, "Cuando Claude Code pregunta algo, "), "la pregunta se convierte en un vector y se devuelven los fragmentos más cercanos (sin gastar tokens)."))),
  ...section("Qué hace cada sección"), h("div", { class: "grid two" }, [["Resumen", "Salud y números clave."], ["Bases de conocimiento", "Tamaño y costo por proyecto; avisos para decidir qué compactar."], ["Vectores", "Qué huellas se guardan y cuánto pesan."], ["Grafo", "El mapa de conceptos."], ["PostgreSQL", "La base de datos, en solo lectura."], ["Búsqueda", "Prueba la recuperación."], ["Tokens y costo", "Consumo de IA, de tres fuentes."], ["API y contenedores", "Quién llama a Cognee y salud de los servicios."]].map(([a, b]) => h("div", { class: "card" }, h("b", {}, a), h("div", { class: "muted" }, b)))),
  ...section("Glosario"), h("div", { class: "card" }, h("dl", { class: "gloss" }, GLOSSARY.flatMap(([t, d]) => [h("dt", {}, t), h("dd", {}, d)])))) };

/* ── navegación y tema ── */
const NAV = [["General", ["resumen"]], ["Conocimiento", ["conocimiento", "vectores", "grafo", "busqueda"]], ["Datos", ["postgres", "sync"]], ["Consumo y salud", ["tokens", "llamadas"]], ["Ayuda", ["guia"]]];
const NAMES = { resumen: "Resumen", conocimiento: "Bases de conocimiento", vectores: "Vectores", grafo: "Grafo", busqueda: "Búsqueda", postgres: "PostgreSQL", sync: "Sincronización", tokens: "Tokens y costo", llamadas: "API y contenedores", guia: "Guía y glosario" };
function themeBtn() {
  const dark = document.documentElement.dataset.theme === "dark";
  return h("button", { class: "ghost", id: "themeBtn", title: "Cambiar tema", "aria-label": "Cambiar tema", onclick: () => { const d = document.documentElement.dataset.theme !== "dark"; document.documentElement.dataset.theme = d ? "dark" : "light"; try { localStorage.setItem("mm-theme", d ? "dark" : "light"); } catch (_) { /* sin almacenamiento */ } $("#themeBtn").replaceWith(themeBtn()); } }, icon(dark ? "sun" : "moon", 15));
}
function route() {
  const key = (location.hash || "#resumen").slice(1), p = pages[key] || pages.resumen;
  document.querySelectorAll("#menu a").forEach((a) => a.classList.toggle("on", a.dataset.k === (pages[key] ? key : "resumen")));
  $("#title").textContent = p.title; $("#subtitle").textContent = p.sub; document.title = `${p.title} · Management Memory`; $("#side").classList.remove("open");
  $("#actions").replaceChildren(h("button", { class: "ghost", onclick: route, title: "Volver a cargar los datos" }, icon("refresh", 15), " Actualizar"), themeBtn());
  render(p.run);
}
try { const t = localStorage.getItem("mm-theme") || (matchMedia("(prefers-color-scheme:dark)").matches ? "dark" : "light"); document.documentElement.dataset.theme = t; } catch (_) { /* tema por defecto */ }
$("#menu").append(...NAV.flatMap(([g, keys]) => [h("div", { class: "group" }, g), ...keys.map((k) => h("a", { data: { k }, href: "#" + k }, icon(pages[k].icon, 18), NAMES[k]))]));
$("#menuBtn").onclick = () => $("#side").classList.toggle("open");
addEventListener("hashchange", route); route();
setInterval(() => { $("#clock").textContent = new Date().toLocaleTimeString("es-CO"); }, 1000);
