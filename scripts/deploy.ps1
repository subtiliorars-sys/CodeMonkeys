#!/usr/bin/env pwsh
# Deploy CodeMonkeys to Fly, always forcing a fresh `static/` layer.
# Depot's remote builder was observed serving a stale COPY static/ layer even
# after content changed; the Dockerfile's CACHEBUST build-arg (used right
# before COPY static/) forces that layer to invalidate on every deploy.
$cachebust = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
fly deploy --app codemonkeys --remote-only --build-arg "CACHEBUST=$cachebust"
