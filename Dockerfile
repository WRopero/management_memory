FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
# Libreria del grafo (cytoscape.js) fijada y descargada al construir: la UI no depende de CDN al ejecutarse.
RUN python - <<'PY'
import hashlib, pathlib, urllib.request
url = "https://cdn.jsdelivr.net/npm/cytoscape@3.30.2/dist/cytoscape.min.js"
data = urllib.request.urlopen(url, timeout=60).read()
out = pathlib.Path("static/vendor"); out.mkdir(parents=True, exist_ok=True)
(out / "cytoscape.min.js").write_bytes(data)
print("cytoscape.min.js", len(data), "bytes sha256", hashlib.sha256(data).hexdigest())
PY
RUN chown -R 10001:10001 /srv
USER 10001:10001
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
