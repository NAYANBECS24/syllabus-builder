#!/usr/bin/env python3
"""
Vercel Universal Serverless Function Entry Point: /api and /api/*
Routes all requests to sylex_server.Handler methods.
"""

import sys
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sylex_server import Handler

class handler(Handler):
    def do_OPTIONS(self):
        super().do_OPTIONS()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.lstrip('/')

        # Handle root /api
        if path in ("api", "api/", ""):
            body = json.dumps({
                "name": "SYLEX Syllabus Extraction API",
                "version": "3.0",
                "status": "online",
                "platform": "vercel-serverless",
                "endpoints": [
                    "/api/status",
                    "/api/extract",
                    "/api/chat",
                    "/api/test-key",
                    "/api/curriculum-audit",
                    "/api/export-dossier"
                ]
            }, indent=2).encode('utf-8')
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.lstrip('/')

        if path in ("api", "api/", ""):
            self.do_GET()
            return

        super().do_POST()
