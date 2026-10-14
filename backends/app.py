"""Tiny test backend for the load balancer.

Config via environment variables:
  NAME        name reported in responses (default: backend)
  PORT        port to listen on (default: 8080)
  DELAY_MS    artificial latency added to every request (default: 0)
  ERROR_RATE  fraction of requests that fail with 500, 0.0-1.0 (default: 0)
"""
import json
import os
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NAME = os.getenv("NAME", "backend")
PORT = int(os.getenv("PORT", "8080"))
DELAY_MS = int(os.getenv("DELAY_MS", "0"))
ERROR_RATE = float(os.getenv("ERROR_RATE", "0"))


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        # Health checks must stay fast and reliable, so skip delay and errors.
        if self.path == "/health":
            self._send(200, {"status": "ok", "backend": NAME})
            return

        if DELAY_MS:
            time.sleep(DELAY_MS / 1000)

        if random.random() < ERROR_RATE:
            self._send(500, {"error": "injected failure", "backend": NAME})
            return

        self._send(200, {"backend": NAME, "path": self.path})

    def log_message(self, fmt, *args):
        print(f"[{NAME}] {self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    print(f"[{NAME}] listening on :{PORT} delay={DELAY_MS}ms error_rate={ERROR_RATE}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
