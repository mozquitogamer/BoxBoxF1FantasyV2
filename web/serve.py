"""Simple HTTP server with no caching for local dev."""
import http.server
import os
import sys

SERVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SERVE_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

print(f"Serving {SERVE_DIR} on port 3000", flush=True)
http.server.HTTPServer(("127.0.0.1", 3000), NoCacheHandler).serve_forever()
