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
COPY feedback_triage.py .
COPY corps/ corps/
COPY scripts/ scripts/

# Depot's remote builder was observed serving a stale `COPY static/` layer even
# after the source content changed, requiring a hand-edited date comment above
# this line before every deploy to force a rebuild. Replaced with an ARG that
# `fly deploy` supplies automatically (see fly.toml / docs/STATE.md "Deploy") —
# every deploy gets a fresh value, so the static layer's cache key always
# changes and no one has to remember to bump anything by hand.
ARG CACHEBUST=dev
RUN echo "$CACHEBUST" > /tmp/.cachebust
COPY static/ static/

# Vendor Tailwind (Wave 4 #3): compile the utility CSS the frontend uses into a
# static file (Node/npm already present for stdio MCP). This is what lets us drop
# the runtime cdn.tailwindcss.com <script> and tighten the CSP. --minify keeps it
# small; pinned version for reproducibility.
COPY tailwind.config.js .
RUN npx --yes tailwindcss@3.4.17 \
      -i static/forge/tailwind.input.css \
      -o static/forge/tailwind.css --minify

ENV DATA_DIR=/data PORT=8080
EXPOSE 8080
# --proxy-headers lets uvicorn trust the Fly proxy's X-Forwarded-Proto/Host headers
# so request.base_url resolves to the real https URL (needed for correct redirect_uri
# derivation in the OAuth flow). --forwarded-allow-ips is scoped to Fly's private 6PN
# network (172.16.0.0/12), not '*' — only the Fly proxy can reach this container, so
# trust that range rather than any client that manages to connect.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips=172.16.0.0/12"]
