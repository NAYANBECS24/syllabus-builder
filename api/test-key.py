#!/usr/bin/env python3
"""Vercel Serverless Function: POST /api/test-key"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sylex_server import Handler


class handler(Handler):
    def do_OPTIONS(self):
        super().do_OPTIONS()

    def do_POST(self):
        self.path = "/api/test-key"
        super().do_POST()

    def do_GET(self):
        self.send_json({"error": "Method not allowed. Use POST /api/test-key"}, 405)
