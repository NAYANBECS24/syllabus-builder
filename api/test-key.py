#!/usr/bin/env python3
"""Vercel Serverless Function: POST /api/test-key"""

import json
import time
import sys
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        self.end_headers()

    def send_json(self, data, code=200):
        body = json.dumps(data, indent=2).encode('utf-8')
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else b'{}'
            req_data = json.loads(body.decode('utf-8')) if body else {}

            provider = req_data.get("provider", "nvidia").lower()
            key = req_data.get("key", "").strip()
            model = req_data.get("model", "").strip()
            endpoint = req_data.get("endpoint", "").strip()

            t0 = time.time()

            if provider == "nvidia":
                apiKey = key or "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"
                base_url = endpoint.rstrip('/') if endpoint else "https://integrate.api.nvidia.com/v1"
                req_model = model or "nvidia/nemotron-3-super-120b-a12b"
                url = f"{base_url}/chat/completions"
                payload = {
                    "model": req_model,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant. Reply concisely."},
                        {"role": "user", "content": "Ping: confirm system status."}
                    ],
                    "max_tokens": 64,
                    "temperature": 0.2
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {apiKey}"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    content = data["choices"][0]["message"].get("content", "")
                    elapsed = int((time.time() - t0) * 1000)
                    self.send_json({
                        "status": "ok",
                        "provider": "nvidia",
                        "model": req_model,
                        "latency_ms": elapsed,
                        "content": content.strip()
                    })
                    return

            elif provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    elapsed = int((time.time() - t0) * 1000)
                    self.send_json({"status": "ok", "provider": "gemini", "latency_ms": elapsed})
                return

            elif provider == "openai":
                url = "https://api.openai.com/v1/models"
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    elapsed = int((time.time() - t0) * 1000)
                    self.send_json({"status": "ok", "provider": "openai", "latency_ms": elapsed})
                return

            elif provider == "custom":
                url = (endpoint.rstrip('/') if endpoint else "http://localhost:11434/v1") + "/models"
                headers = {"Authorization": f"Bearer {key}"} if key else {}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    elapsed = int((time.time() - t0) * 1000)
                    self.send_json({"status": "ok", "provider": "custom", "latency_ms": elapsed})
                return

            else:
                self.send_json({"error": f"Unknown provider: {provider}"}, 400)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)
