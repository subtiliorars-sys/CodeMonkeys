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
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
