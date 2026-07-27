# services/finlynq/Dockerfile
#
# Phase F1 — minimal FastAPI image. Phase F3-F4 will add system deps for
# pdfplumber / pytesseract / pandas / ofxparse. Until that lands the image
# stays slim to keep CI runs fast.
#
# Mirrors services/telegram-gateway/Dockerfile's shape but with the real
# uvicorn entry point. Both services share the project-root ``.venv`` so
# the same Python interpreter + pinned versions power both.

FROM python:3.12-slim

WORKDIR /app

# Install Finlynq deps. `pip install --no-cache-dir` keeps the layer small.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the service source.
COPY app/ ./app/
COPY tests/ ./tests/
COPY pytest.ini .

# Finlynq listens on API_PORT (default 8001). Exposed to host via
# docker-compose.yml's `finlynq` port mapping.
EXPOSE 8001

# Run uvicorn. `--host 0.0.0.0` so docker-compose port-forwarding reaches
# the listener; `--port 8001` matches FINLYNQ_URL=http://localhost:8001
# declared in .env.example.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
