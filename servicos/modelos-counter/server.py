#!/usr/bin/env python3
"""Simple visit counter for the modelos gallery."""
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

COUNTER_FILE = "/var/www/modelos-counter/visits.txt"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Read current count
        count = 0
        if os.path.exists(COUNTER_FILE):
            try:
                with open(COUNTER_FILE, "r") as f:
                    count = int(f.read().strip())
            except (ValueError, IOError):
                count = 0

        # Increment
        count += 1
        with open(COUNTER_FILE, "w") as f:
            f.write(str(count))

        # Return JSON
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"visits": count}).encode())

    def log_message(self, format, *args):
        pass  # Suppress logs

if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 9002), Handler)
    print("Modelos visit counter running on port 9002")
    server.serve_forever()
