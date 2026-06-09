#!/usr/bin/env python3
"""
🌉 Cline Proxy — Local API Proxy Server
=========================================
OpenAI-compatible local proxy for Cline VS Code extension.

Routes requests through multiple providers (OpenRouter, Gemini,
Anthropic, Ollama) with automatic fallback and key rotation.

Usage:
  python3 cline_proxy.py                    # Default port 4891
  python3 cline_proxy.py --port 8080        # Custom port
  python3 cline_proxy.py --verbose          # Verbose logging
  python3 cline_proxy.py --config-dir /path # Custom config dir

Cline Configuration (VS Code settings.json):
  "cline.apiProvider": "openai",
  "cline.openAiApiUrl": "http://localhost:4891/v1",
  "cline.openAiModel": "fast",
  "cline.openAiKey": "proxy-local"
"""

import argparse
import json
import os
import signal
import socketserver
import sys
import time
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

from proxy_config import (
    ProxyConfig,
    load_aliases,
    get_all_model_entries,
    ensure_config_dir,
    get_provider_key_strings,
    ALIAS_TABLE,
)
from proxy_router import (
    build_adapter_chain,
    route_request,
    RequestNormalizer,
    resolve_model,
    get_route_stats,
)
from proxy_streaming import stream_to_sse, format_error, openai_chunk_wrap


# ── Threaded HTTP Server ────────────────────────────────────────

class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Handle requests in separate threads for concurrent connections."""
    allow_reuse_address = True
    daemon_threads = True


# ── Request Handler ──────────────────────────────────────────────

class ClineProxyHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for the Cline proxy server.

    Implements the OpenAI-compatible API:
      GET  /v1/models             → List available models
      POST /v1/chat/completions    → Chat completion (streaming + non-streaming)
      GET  /v1/proxy/status        → Proxy health & stats
      OPTIONS *                    → CORS preflight
    """

    # Shared across all handler instances
    server_config: ProxyConfig = None
    adapter_chain: list = []

    def log_message(self, format, *args):
        """Suppress default HTTP log unless verbose."""
        if self.server_config and self.server_config.verbose:
            super().log_message(format, *args)

    # ── CORS Headers ────────────────────────────────────────────

    def _set_cors_headers(self):
        """Set CORS headers on every response."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, Authorization, X-Requested-With")
        self.send_header("Access-Control-Max-Age", "86400")

    def _send_json(self, status_code: int, data: dict):
        """Send a JSON response with proper headers."""
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status_code: int, message: str,
                         error_type: str = "api_error"):
        """Send a JSON error response."""
        self._send_json(status_code, format_error(error_type, message))

    # ── OPTIONS ─────────────────────────────────────────────────

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    # ── GET ─────────────────────────────────────────────────────

    def do_GET(self):
        """Handle GET requests."""
        path = self.path.rstrip("/")

        if path == "/v1/models" or path == "/v1/models/":
            self._handle_models()
        elif path == "/v1/proxy/status" or path == "/v1/proxy/status/":
            self._handle_status()
        elif path == "/health" or path == "/":
            self._send_json(200, {
                "status": "ok",
                "service": "cline-proxy",
                "version": "1.0.0",
            })
        else:
            self._send_error_json(404, f"Not found: {path}")

    def _handle_models(self):
        """Return list of available models in OpenAI format."""
        aliases = load_aliases(
            self.server_config.alias_file if self.server_config else None
        )
        models = get_all_model_entries(aliases)
        self._send_json(200, {
            "object": "list",
            "data": models,
        })

    def _handle_status(self):
        """Return proxy status with redacted keys."""
        stats = get_route_stats()

        # Add provider key info (redacted)
        provider_keys = {}
        for provider in ("openrouter", "gemini", "anthropic", "ollama"):
            keys = get_provider_key_strings(provider)
            redacted = []
            for k in keys:
                if k == "ollama-local":
                    redacted.append("ollama-local")
                elif len(k) > 8:
                    # Strip common key prefixes for safe display
                    display = k
                    for prefix in ("sk-", "AIza", "anthropic-", "sk-ant-"):
                        if display.startswith(prefix):
                            display = display[len(prefix):]
                            break
                    redacted.append(f"...{display[-4:]}")
                else:
                    redacted.append("***")
            provider_keys[provider] = {
                "count": len(keys),
                "keys": redacted,
            }

        # Adapter availability
        adapters_status = []
        for adapter in self.adapter_chain:
            adapters_status.append({
                "provider": adapter.provider_name,
                "available": adapter.is_available(),
            })

        self._send_json(200, {
            "status": "running",
            "port": self.server.server_port if hasattr(self.server, 'server_port') else "?",
            "uptime_seconds": time.time() - startup_time,
            "providers": provider_keys,
            "adapters": adapters_status,
            "stats": stats,
            "config": {
                "alias_count": len(load_aliases()),
                "verbose": self.server_config.verbose if self.server_config else False,
            },
        })

    # ── POST ────────────────────────────────────────────────────

    def do_POST(self):
        """Handle POST requests."""
        path = self.path.rstrip("/")

        if path == "/v1/chat/completions" or path == "/v1/chat/completions/":
            self._handle_chat()
        else:
            self._send_error_json(404, f"Not found: {path}")

    def _handle_chat(self):
        """Handle chat completion requests (streaming + non-streaming)."""
        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self._send_error_json(400, "Request body is empty")
            return

        try:
            raw_body = self.rfile.read(content_length)
            payload = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._send_error_json(400, f"Invalid JSON: {e}")
            return

        # Normalize payload
        normalizer = RequestNormalizer()
        payload = normalizer.normalize(payload)

        stream = payload.get("stream", False)
        model = payload.get("model", "fast")

        # Route the request
        try:
            result = route_request(payload, self.adapter_chain, self.server_config)
        except Exception as e:
            # Catch-all: never let raw exceptions reach Cline
            err_msg = f"{type(e).__name__}: {str(e)[:200]}"
            if self.server_config and self.server_config.verbose:
                traceback.print_exc()
            self._send_error_json(500, err_msg)
            return

        if stream:
            # Streaming response
            if isinstance(result, dict) and "error" in result:
                # Error from router
                self._send_json(503, result)
                return

            if not isinstance(result, type(iter([]))):
                # Got a non-iterator for stream request — handle gracefully
                if isinstance(result, dict):
                    # Convert non-streaming response to streaming format
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    finish = result.get("choices", [{}])[0].get("finish_reason", "stop")

                    def _make_stream():
                        if content:
                            yield openai_chunk_wrap(content, model)
                        yield openai_chunk_wrap("", model, finish)
                        yield "[DONE]"

                    result = _make_stream()
                else:
                    self._send_error_json(500, "Unexpected response format for stream request")
                    return

            # Stream the response via SSE
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self._set_cors_headers()
            self.end_headers()

            try:
                for sse_chunk in stream_to_sse(result):
                    self.wfile.write(sse_chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                # Client disconnected — stop streaming gracefully
                pass
        else:
            # Non-streaming response
            if isinstance(result, dict):
                if "error" in result:
                    self._send_json(503, result)
                else:
                    self._send_json(200, result)
            else:
                # Got an iterator for non-stream request — drain it
                try:
                    from proxy_streaming import drain_to_json
                    full_result = drain_to_json(result, model)
                    self._send_json(200, full_result)
                except Exception as e:
                    self._send_error_json(500, f"Failed to assemble response: {e}")


# ── Startup Time ────────────────────────────────────────────────

startup_time = time.time()


# ── Main ────────────────────────────────────────────────────────

def main():
    global startup_time

    parser = argparse.ArgumentParser(
        description="🌉 Cline Proxy — Local API Proxy for Cline VS Code Extension",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 cline_proxy.py                    # Default port 4891
  python3 cline_proxy.py --port 8080        # Custom port
  python3 cline_proxy.py --verbose          # Debug logging

Cline Configuration:
  Set "cline.openAiApiUrl": "http://localhost:4891/v1"
  Set "cline.openAiModel": "fast"
  Set "cline.openAiKey": "proxy-local"
        """,
    )
    parser.add_argument(
        "--port", type=int, default=4891,
        help="Port to listen on (default: 4891)",
    )
    parser.add_argument(
        "--config-dir", type=str, default="",
        help="Config directory (default: ~/.banana_shelter)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose logging",
    )
    parser.add_argument(
        "--host", type=str, default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )

    args = parser.parse_args()

    # ── Build config ────────────────────────────────────────────
    config = ProxyConfig(
        port=args.port,
        config_dir=args.config_dir,
        verbose=args.verbose,
    )

    ensure_config_dir(config.config_dir)

    # ── Build adapter chain ─────────────────────────────────────
    adapters = build_adapter_chain(config)

    # ── Setup server ────────────────────────────────────────────
    ClineProxyHandler.server_config = config
    ClineProxyHandler.adapter_chain = adapters

    server = ThreadingHTTPServer((args.host, config.port), ClineProxyHandler)

    # ── Print banner ────────────────────────────────────────────
    print()
    print("  🌉  Cline Proxy Server  —  v1.0")
    print("  ═══════════════════════════════════")
    print(f"  📡  Listening on http://{args.host}:{config.port}/v1")
    print()

    # Show provider availability
    print("  📡  Provider Status:")
    for adapter in adapters:
        marker = "🟢" if adapter.is_available() else "🔴"
        keys = get_provider_key_strings(adapter.provider_name)
        key_count = len(keys)
        print(f"     {marker} {adapter.provider_name:12s} ({key_count} key{'s' if key_count != 1 else ''})")
    print()

    # Show built-in aliases
    aliases = load_aliases()
    print(f"  🎯  Model Aliases ({len(aliases)}):")
    for alias, info in aliases.items():
        print(f"     {alias:12s} → {info['provider']:12s} {info['model_id']}")
    print()

    if not adapters:
        print("  ⚠️  No providers configured!")
        print("     Run config_manager.py to add API keys.")
        print("     Without keys, all requests will fail.")
        print(f"     Config file: {config.config_dir}/config.json")
        print()

    print(f"  🚀  Server starting...")
    print(f"  🔗  Point Cline to: http://{args.host}:{config.port}/v1")
    print(f"  💡  Use model 'fast' in Cline for cheapest routing")
    print(f"  🛑  Press Ctrl+C to stop")
    print()

    # ── Signal handling ─────────────────────────────────────────
    shutdown_event = [False]

    def signal_handler(sig, frame):
        if shutdown_event[0]:
            print("\n  ⚠️  Force exit")
            sys.exit(1)
        shutdown_event[0] = True
        print("\n\n  🛑  Shutting down...")
        server.shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # ── Serve ───────────────────────────────────────────────────
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("  ✅  Proxy stopped")
        print()


if __name__ == "__main__":
    main()
