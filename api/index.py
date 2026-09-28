#!/usr/bin/env python3
"""
SYLEX Universal Syllabus Extractor — Vercel Serverless Function Entry Point
Enables seamless cloud deployment on Vercel with zero-configuration serverless functions.
"""

import sys
import os
from pathlib import Path
from urllib.parse import urlparse

# Ensure root directory is on Python path to resolve sylex and sylex_server
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from sylex_server import Handler
except ImportError:
    import sylex_server
    Handler = sylex_server.Handler


class handler(Handler):
    """Vercel Serverless Function HTTP Request Handler."""

    def _normalize_vercel_path(self):
        """Map Vercel internal rewrite paths back to the intended API endpoint."""
        matched = self.headers.get("x-matched-path") or self.headers.get("x-forwarded-uri") or ""
        if matched and "/api/" in matched:
            self.path = matched
        elif self.path.startswith("/api/index.py"):
            parsed = urlparse(self.path)
            q = parsed.query
            if "path=" in q:
                for param in q.split("&"):
                    if param.startswith("path="):
                        self.path = "/" + param.split("=", 1)[1]
            else:
                self.path = "/api/" + self.path[len("/api/index.py"):].lstrip('/')

    def do_OPTIONS(self):
        self._normalize_vercel_path()
        super().do_OPTIONS()

    def do_GET(self):
        self._normalize_vercel_path()
        super().do_GET()

    def do_POST(self):
        self._normalize_vercel_path()
        super().do_POST()
