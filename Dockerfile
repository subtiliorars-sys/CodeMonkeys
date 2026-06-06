FROM python:3.12-slim

# nodejs + npm enable stdio MCP servers (e.g. npx @modelcontextprotocol/server-filesystem)
# Cost: ~80 MB added to image; acceptable for stdio MCP support.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git grep curl ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY corps/ corps/
COPY static/ static/
COPY scripts/ scripts/

ENV DATA_DIR=/data PORT=8080
EXPOSE 8080
# --proxy-headers + --forwarded-allow-ips=* let uvicorn trust the Fly proxy's
# X-Forwarded-Proto/Host headers so request.base_url resolves to the real https URL
# (needed for correct redirect_uri derivation in the OAuth flow).
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
