#!/usr/bin/env python3
"""Vercel Serverless Function: POST /api/chat"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sylex_server import Handler

class handler(Handler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        self.end_headers()

    def do_POST(self):
        self.path = "/api/chat"
        super().do_POST()

    def do_GET(self):
        self.send_json({"error": "Method not allowed. Use POST /api/chat"}, 405)
