#!/usr/bin/env python3
"""Vercel Serverless Function: POST /api/test-key"""

import json
import os
import time
import sys
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

def _load_local_env():
    """Load local secrets without affecting Vercel's managed environment."""
    env_file = ROOT_DIR / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name and name not in os.environ:
            os.environ[name] = value.strip().strip('"').strip("'")

_load_local_env()

DEFAULT_NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "").strip()

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
                apiKey = key or DEFAULT_NVIDIA_API_KEY
                if not apiKey:
                    self.send_json(
                        {"error": "No NVIDIA API key configured. Set NVIDIA_API_KEY on the server or supply one in the request."},
                        400,
                    )
                    return
                base_url = endpoint.rstrip('/') if endpoint else "https://integrate.api.nvidia.com/v1"
                req_model = model or "z-ai/glm-5.3"
                url = f"{base_url}/models"
                req = urllib.request.Request(
                    url,
                    headers={
                        "Authorization": f"Bearer {apiKey}"
                    },
                    method="GET"
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    available_models = {item.get("id") for item in data.get("data", [])}
                    if req_model not in available_models:
                        self.send_json({"error": f"Configured model is not available: {req_model}"}, 400)
                        return
                    elapsed = int((time.time() - t0) * 1000)
                    self.send_json({
                        "status": "ok",
                        "provider": "nvidia",
                        "model": req_model,
                        "latency_ms": elapsed
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
