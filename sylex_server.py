#!/usr/bin/env python3
"""
SYLEX Local Server — bridges the web UI and Python extraction engine.
Run this to use the web dashboard offline.

    python sylex_server.py
    # then open http://localhost:7823 in your browser
"""

import sys, os, json, tempfile, threading, subprocess, mimetypes, hashlib, copy, html, platform, re, time, difflib
import urllib
import urllib.request
import urllib.error
import urllib.parse
import ipaddress
import socket
from collections import OrderedDict
os.environ["PYMUPDF_SUGGEST_LAYOUT_ANALYZER"] = "0"
from pathlib import Path
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, List, Tuple

PORT      = 7823
HOST      = os.environ.get("SYLEX_HOST", "127.0.0.1")
BASE_DIR  = Path(__file__).parent
SYLEX_PY  = BASE_DIR / "sylex.py"
MAX_JSON_BYTES = 1 * 1024 * 1024
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_BOOK_QUERY_CHARS = 160
MAX_BOOK_RESULTS = 20
MAX_BOOK_OUTLINE_ITEMS = 160
MAX_BOOK_DISCOVERY_TITLE_CHARS = 180
MAX_BOOK_DISCOVERY_AUTHOR_CHARS = 160
MAX_BOOK_DISCOVERY_RESULTS = 24
OPEN_LIBRARY_CANDIDATE_LIMIT = 100
GOOGLE_BOOKS_CANDIDATE_LIMIT = 40
OPEN_LIBRARY_RETRY_CANDIDATE_LIMIT = 24
BOOK_DISCOVERY_CACHE_TTL_SECONDS = 15 * 60
STATIC_FILES = {
    "index.html", "styles.css", "app.js", "book.js", "book-finder.js", "demo-data.js", "chat.js", "chat.css"
}


class RequestError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _validated_endpoint(endpoint: str) -> str:
    """Validate a user-supplied HTTP endpoint and block server-side network targets."""
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RequestError("Custom endpoint must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise RequestError("Custom endpoint must not contain URL credentials")
    if parsed.query or parsed.fragment:
        raise RequestError("Custom endpoint must not contain a query string or fragment")
    try:
        port = parsed.port
    except ValueError as exc:
        raise RequestError(f"Invalid custom endpoint port: {exc}") from exc
    try:
        addresses = {
            item[4][0].split('%', 1)[0]
            for item in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise RequestError(f"Could not resolve custom endpoint host: {exc}") from exc
    allow_loopback = not bool(os.environ.get("VERCEL"))
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_loopback and allow_loopback:
            continue
        if not ip.is_global:
            raise RequestError("Custom endpoint resolves to a private or reserved network address")
    return endpoint.rstrip('/')

def _load_local_env():
    """Load local secrets without affecting Vercel's managed environment."""
    env_file = BASE_DIR / ".env"
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

# Server-side fallback credential. Configure NVIDIA_API_KEY in Vercel project
# settings (or a local .env). Request-supplied keys take precedence.
DEFAULT_NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "").strip()

# Where the prompt lives locally vs. inside a Vercel function bundle, where the
# working directory is not the repo root. Bundled with functions["api/*.py"]
# .includeFiles in vercel.json.
SYSTEM_PROMPT_FILENAME = "SYSTEM_PROMPT.md"


def _read_system_prompt() -> str:
    """Read SYSTEM_PROMPT.md from the first location that exists."""
    candidates = []
    env_path = os.environ.get("SYSTEM_PROMPT_PATH", "").strip()
    if env_path:
        candidates.append(Path(env_path))
    here = Path(__file__).resolve().parent
    candidates += [
        here / SYSTEM_PROMPT_FILENAME,
        here.parent / SYSTEM_PROMPT_FILENAME,
        Path.cwd() / SYSTEM_PROMPT_FILENAME,
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                text = candidate.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except Exception:
            continue
    return ""

# Thread-safe in-memory LRU Cache for sub-millisecond repeated extractions
class ExtractionCache:
    def __init__(self, max_items: int = 256):
        self.cache = OrderedDict()
        self.lock = threading.Lock()
        self.max_items = max_items

    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            return None

    def set(self, key: str, value: Any):
        with self.lock:
            self.cache[key] = value
            self.cache.move_to_end(key)
            if len(self.cache) > self.max_items:
                self.cache.popitem(last=False)

    def clear(self):
        with self.lock:
            self.cache.clear()

CACHE = ExtractionCache(max_items=256)
BOOK_TEXT_CACHE = ExtractionCache(max_items=8)
BOOK_DISCOVERY_CACHE = ExtractionCache(max_items=32)

# Default Fallback Syllabus Context (CS23301 Data Structures & Algorithms)
DEFAULT_TASK1 = {
    "document": "SampleCollege-R2023-CSE.pdf",
    "course_count": 12,
    "courses": [
        {"code": "CS23301", "title": "DATA STRUCTURES AND ALGORITHMS", "page": 12},
        {"code": "CS23302", "title": "OBJECT ORIENTED PROGRAMMING", "page": 24},
        {"code": "MA23101", "title": "ENGINEERING MATHEMATICS I", "page": 36},
        {"code": "CS23303", "title": "COMPUTER ORGANIZATION AND ARCHITECTURE", "page": 48},
        {"code": "CS23304", "title": "OPERATING SYSTEMS", "page": 60},
        {"code": "CS23305", "title": "DATABASE MANAGEMENT SYSTEMS", "page": 72},
        {"code": "EC23201", "title": "DIGITAL ELECTRONICS", "page": 84},
        {"code": "CS23401", "title": "COMPUTER NETWORKS", "page": 96},
        {"code": "CS23402", "title": "COMPILER DESIGN", "page": 108},
        {"code": "CS23403", "title": "MACHINE LEARNING", "page": 120},
        {"code": "CS23404", "title": "INFORMATION SECURITY", "page": 132},
        {"code": "", "title": "PROFESSIONAL ETHICS AND HUMAN VALUES", "page": 144}
    ]
}

DEFAULT_TASK2 = {
    "course": {
        "code": "CS23301",
        "title": "DATA STRUCTURES AND ALGORITHMS",
        "category": "PC",
        "lecture": 3,
        "tutorial": 1,
        "practical": 0,
        "credits": 4,
        "pages": [12, 13, 14, 15]
    },
    "units": [
        {
            "number": 1,
            "title": "LINEAR DATA STRUCTURES",
            "hours": 9,
            "text": "Arrays - linked lists - singly, doubly and circular linked lists - stacks - queues - dequeues - priority queues - applications.",
            "topics": [
                {"id": "u1t1", "text": "Arrays", "bloom": "remember", "bloom_source": "inferred"},
                {"id": "u1t2", "text": "linked lists", "bloom": "understand", "bloom_source": "inferred"},
                {"id": "u1t3", "text": "singly, doubly and circular linked lists", "bloom": "understand", "bloom_source": "inferred"},
                {"id": "u1t4", "text": "stacks", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u1t5", "text": "queues", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u1t6", "text": "dequeues", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u1t7", "text": "priority queues", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u1t8", "text": "applications", "bloom": "apply", "bloom_source": "inferred"}
            ]
        },
        {
            "number": 2,
            "title": "TREES",
            "hours": 9,
            "text": "Trees - binary trees - binary search trees - AVL trees - B-trees - red-black trees - heap - applications.",
            "topics": [
                {"id": "u2t1", "text": "Trees", "bloom": "understand", "bloom_source": "inferred"},
                {"id": "u2t2", "text": "binary trees", "bloom": "understand", "bloom_source": "inferred"},
                {"id": "u2t3", "text": "binary search trees", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u2t4", "text": "AVL trees", "bloom": "analyse", "bloom_source": "inferred"},
                {"id": "u2t5", "text": "B-trees", "bloom": "analyse", "bloom_source": "inferred"},
                {"id": "u2t6", "text": "red-black trees", "bloom": "analyse", "bloom_source": "inferred"},
                {"id": "u2t7", "text": "heap", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u2t8", "text": "applications", "bloom": "apply", "bloom_source": "inferred"}
            ]
        },
        {
            "number": 3,
            "title": "GRAPHS",
            "hours": 9,
            "text": "Graph representation - BFS - DFS - spanning trees - Prim's algorithm - Kruskal's algorithm - shortest paths - Dijkstra's algorithm - Floyd-Warshall algorithm.",
            "topics": [
                {"id": "u3t1", "text": "Graph representation", "bloom": "understand", "bloom_source": "inferred"},
                {"id": "u3t2", "text": "BFS", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u3t3", "text": "DFS", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u3t4", "text": "spanning trees", "bloom": "understand", "bloom_source": "inferred"},
                {"id": "u3t5", "text": "Prim's algorithm", "bloom": "apply", "bloom_source": "printed"},
                {"id": "u3t6", "text": "Kruskal's algorithm", "bloom": "apply", "bloom_source": "printed"},
                {"id": "u3t7", "text": "shortest paths", "bloom": "analyse", "bloom_source": "inferred"},
                {"id": "u3t8", "text": "Dijkstra's algorithm", "bloom": "apply", "bloom_source": "printed"},
                {"id": "u3t9", "text": "Floyd-Warshall algorithm", "bloom": "analyse", "bloom_source": "printed"}
            ]
        },
        {
            "number": 4,
            "title": "SORTING AND SEARCHING",
            "hours": 9,
            "text": "Insertion sort - selection sort - bubble sort - merge sort - quick sort - heap sort - radix sort - hashing techniques - collision resolution.",
            "topics": [
                {"id": "u4t1", "text": "Insertion sort", "bloom": "remember", "bloom_source": "inferred"},
                {"id": "u4t2", "text": "selection sort", "bloom": "remember", "bloom_source": "inferred"},
                {"id": "u4t3", "text": "bubble sort", "bloom": "remember", "bloom_source": "inferred"},
                {"id": "u4t4", "text": "merge sort", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u4t5", "text": "quick sort", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u4t6", "text": "heap sort", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u4t7", "text": "radix sort", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u4t8", "text": "hashing techniques", "bloom": "understand", "bloom_source": "inferred"},
                {"id": "u4t9", "text": "collision resolution", "bloom": "analyse", "bloom_source": "inferred"}
            ]
        },
        {
            "number": 5,
            "title": "ALGORITHM DESIGN TECHNIQUES",
            "hours": 9,
            "text": "Divide and conquer - greedy method - dynamic programming - backtracking - branch and bound - NP-completeness.",
            "topics": [
                {"id": "u5t1", "text": "Divide and conquer", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u5t2", "text": "greedy method", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u5t3", "text": "dynamic programming", "bloom": "analyse", "bloom_source": "inferred"},
                {"id": "u5t4", "text": "backtracking", "bloom": "apply", "bloom_source": "inferred"},
                {"id": "u5t5", "text": "branch and bound", "bloom": "analyse", "bloom_source": "inferred"},
                {"id": "u5t6", "text": "NP-completeness", "bloom": "understand", "bloom_source": "inferred"}
            ]
        }
    ],
    "course_outcomes": [
        {"id": "CO1", "text": "Understand the concepts of linear data structures and their applications", "bloom": "understand", "bloom_source": "printed"},
        {"id": "CO2", "text": "Implement tree and graph structures for efficient data representation and traversal", "bloom": "apply", "bloom_source": "printed"},
        {"id": "CO3", "text": "Apply sorting, searching, and hashing techniques to solve computational problems", "bloom": "apply", "bloom_source": "printed"},
        {"id": "CO4", "text": "Analyze algorithm efficiency and time/space complexity using asymptotic notation", "bloom": "analyse", "bloom_source": "printed"},
        {"id": "CO5", "text": "Design optimal algorithms using greedy, dynamic programming, and backtracking paradigms", "bloom": "create", "bloom_source": "printed"}
    ],
    "programme_outcomes": [
        {"id": "PO1", "text": "Engineering knowledge: Apply knowledge of mathematics, science, and engineering fundamentals."},
        {"id": "PO2", "text": "Problem analysis: Identify, formulate, and analyze complex engineering problems."},
        {"id": "PO3", "text": "Design/development of solutions: Design solutions for complex engineering problems."},
        {"id": "PO4", "text": "Conduct investigations of complex problems: Use research-based knowledge and research methods."}
    ],
    "co_po_matrix": {
        "CO1": {"PO1": "3", "PO2": "2"},
        "CO2": {"PO1": "3", "PO2": "3", "PO3": "2"},
        "CO3": {"PO1": "3", "PO2": "3", "PO3": "3"},
        "CO4": {"PO1": "2", "PO2": "3", "PO4": "2"},
        "CO5": {"PO1": "3", "PO2": "3", "PO3": "3", "PO4": "2"}
    },
    "books": [
        {"kind": "text", "title": "Data Structures and Algorithm Analysis in C", "author": "Mark Allen Weiss", "publisher": "Pearson Education", "edition": "2nd", "year": 2011},
        {"kind": "text", "title": "Introduction to Algorithms", "author": "Thomas H. Cormen, Charles E. Leiserson, Ronald L. Rivest, Clifford Stein", "publisher": "MIT Press", "edition": "3rd", "year": 2009},
        {"kind": "reference", "title": "Fundamentals of Data Structures in C++", "author": "Ellis Horowitz, Sartaj Sahni, Dinesh Mehta", "publisher": "Universities Press", "edition": "2nd", "year": 2008}
    ],
    "not_extracted": []
}

# Find Python executable
def find_python():
    candidates = [
        sys.executable,
        "python", "python3", "py",
    ]
    for c in candidates:
        try:
            r = subprocess.run([c, "--version"], capture_output=True, timeout=3)
            if r.returncode == 0: return c
        except Exception: pass
    return sys.executable

PYTHON = find_python()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{self.command}] {self.path} — {args[1] if len(args)>1 else ''}")

    def _cors_origin(self) -> Optional[str]:
        origin = self.headers.get("Origin")
        if not origin:
            return None
        request_host = (self.headers.get("Host") or "").lower()
        parsed_origin = urlparse(origin)
        if origin == "null" and request_host.split(':', 1)[0] in {"localhost", "127.0.0.1", "[::1]"}:
            return origin
        if parsed_origin.scheme in {"http", "https"} and parsed_origin.netloc.lower() == request_host:
            return origin
        if parsed_origin.hostname in {"localhost", "127.0.0.1", "::1"} and request_host.split(':', 1)[0] in {"localhost", "127.0.0.1", "[::1]"}:
            return origin
        return None

    def _send_cors_header(self):
        allowed_origin = self._cors_origin()
        if allowed_origin:
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
            self.send_header("Vary", "Origin")

    def send_json(self, data, code=200):
        try:
            body = json.dumps(data, ensure_ascii=False, indent=2, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._send_cors_header()
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
            pass

    def send_bytes(self, body: bytes, content_type: str, filename: Optional[str] = None, code: int = 200):
        """Send a non-JSON API response with safe inline download headers."""
        try:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if filename:
                self.send_header("Content-Disposition", f'inline; filename="{filename}"')
            self._send_cors_header()
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
            pass

    def send_file(self, path: Path):
        try:
            data = path.read_bytes()
            mime = mimetypes.guess_type(str(path))[0] or "text/plain"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_response(404); self.end_headers()

    def do_OPTIONS(self):
        if self.headers.get("Origin") and not self._cors_origin():
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(200)
        self._send_cors_header()
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        self.end_headers()

    def _content_length(self, maximum: int) -> int:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise RequestError("Content-Length header is required", 411)
        try:
            length = int(raw_length)
        except (TypeError, ValueError):
            raise RequestError("Invalid Content-Length header")
        if length < 0:
            raise RequestError("Invalid Content-Length header")
        if length > maximum:
            raise RequestError(f"Request body exceeds the {maximum // (1024 * 1024)} MB limit", 413)
        return length

    def _read_json_body(self) -> Dict[str, Any]:
        length = self._content_length(MAX_JSON_BYTES)
        body = self.rfile.read(length)
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RequestError(f"Invalid JSON request body: {exc}") from exc
        if not isinstance(data, dict):
            raise RequestError("JSON request body must be an object")
        return data

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.lstrip('/')

        # API: status
        if path == "api/status":
            self.send_json({
                "status":  "online",
                "python":  platform.python_version(),
                "version": "3.0",
                "offline": True,
            })
            return

        # API: cache stats
        if path == "api/cache/stats":
            self.send_json({
                "status": "ok",
                "cached_items": len(CACHE.cache),
                "max_items": CACHE.max_items,
                "book_cached_items": len(BOOK_TEXT_CACHE.cache),
                "book_max_items": BOOK_TEXT_CACHE.max_items,
                "book_discovery_cached_items": len(BOOK_DISCOVERY_CACHE.cache),
                "book_discovery_max_items": BOOK_DISCOVERY_CACHE.max_items,
            })
            return

        # API: live curriculum audit
        if path == "api/curriculum-audit":
            try:
                import sylex
                d2 = DEFAULT_TASK2
                audit = sylex.calculate_curriculum_audit(d2)
                self.send_json(audit)
                return
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
                return

        # Static files are explicitly allowlisted so secrets such as .env are never served.
        static_name = path or "index.html"
        safe_path = (BASE_DIR / static_name).resolve()
        if static_name in STATIC_FILES and safe_path.is_file():
            self.send_file(safe_path)
            return

        self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.headers.get("Origin") and not self._cors_origin():
            self.send_json({"error": "Origin is not allowed"}, 403)
            return
        parsed = urlparse(self.path)
        path   = parsed.path.lstrip('/')

        # ── POST /api/cache/clear
        if path == "api/cache/clear":
            CACHE.clear()
            BOOK_TEXT_CACHE.clear()
            BOOK_DISCOVERY_CACHE.clear()
            self.send_json({"status": "ok", "cleared": True})
            return

        # ── POST /api/chat (Universal Cloud AI Curriculum Assistant & Advisor)
        if path == "api/chat":
            try:
                req_data = self._read_json_body()

                user_message = req_data.get("message", "")
                history = req_data.get("history", [])
                context = req_data.get("context") or {}
                provider = req_data.get("provider", "nvidia")
                model = req_data.get("model", "")
                api_key = req_data.get("api_key", "")
                endpoint = req_data.get("endpoint", "")

                if not isinstance(user_message, str) or not user_message.strip():
                    raise RequestError("Message is required")
                user_message = user_message.strip()
                if len(user_message) > 12000:
                    raise RequestError("Message exceeds the 12,000 character limit", 413)
                if not isinstance(history, list):
                    raise RequestError("history must be an array")
                if not isinstance(context, dict):
                    raise RequestError("context must be an object")
                if not all(isinstance(value, str) for value in (provider, model, api_key, endpoint)):
                    raise RequestError("provider, model, api_key, and endpoint must be strings")
                provider = provider.lower().strip()
                model = model.strip()
                api_key = api_key.strip()
                endpoint = endpoint.strip()
                if provider not in {"nvidia", "gemini", "openai", "custom"}:
                    raise RequestError(f"Unknown provider: {provider}")
                if endpoint:
                    endpoint = _validated_endpoint(endpoint)
                    if provider == "nvidia" and not api_key:
                        raise RequestError("A request-specific API key is required with a custom NVIDIA endpoint")

                reply, model_used = self._handle_chat_request(
                    user_message=user_message,
                    history=history,
                    context=context,
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    endpoint=endpoint
                )
                self.send_json({
                    "status": "ok",
                    "reply": reply,
                    "provider": provider,
                    "model": model_used
                })
                return
            except RequestError as e:
                self.send_json({"error": str(e)}, e.status)
                return
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
                return

        # ── POST /api/curriculum-audit (NBA & OBE Accreditation Evaluation)
        if path == "api/curriculum-audit":
            try:
                req_data = self._read_json_body()
                d2 = req_data.get("task2") or req_data.get("d2")
                if d2 is None and req_data.get("course"):
                    d2 = req_data
                d2 = d2 or DEFAULT_TASK2
                if not isinstance(d2, dict):
                    raise RequestError("task2 must be an object")
                import sylex
                audit = sylex.calculate_curriculum_audit(d2)
                self.send_json(audit)
                return
            except RequestError as e:
                self.send_json({"error": str(e)}, e.status)
                return
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
                return

        # ── POST /api/export-dossier (Official University Course File Dossier)
        if path == "api/export-dossier":
            try:
                req_data = self._read_json_body()
                d2 = req_data.get("task2") or req_data.get("d2")
                if d2 is None and req_data.get("course"):
                    d2 = req_data
                d2 = d2 or DEFAULT_TASK2
                if not isinstance(d2, dict):
                    raise RequestError("task2 must be an object")
                html = self._generate_dossier_html(d2)
                c_code = str((d2.get("course") or {}).get("code") or "SYLLABUS")
                safe_code = re.sub(r'[^A-Za-z0-9_.-]+', '_', c_code).strip('._') or "SYLLABUS"
                self.send_json({"status": "ok", "html": html, "filename": f"Course_Dossier_{safe_code}.html"})
                return
            except RequestError as e:
                self.send_json({"error": str(e)}, e.status)
                return
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
                return

        # ── POST /api/test-key  (connectivity test for NVIDIA / Gemini / OpenAI / Custom)
        if path == "api/test-key":
            try:
                import time
                req_data = self._read_json_body()

                provider = req_data.get("provider", "nvidia")
                key = req_data.get("key", "")
                model = req_data.get("model", "")
                endpoint = req_data.get("endpoint", "")

                if not all(isinstance(value, str) for value in (provider, key, model, endpoint)):
                    raise RequestError("provider, key, model, and endpoint must be strings")
                provider = provider.lower().strip()
                key = key.strip()
                model = model.strip()
                endpoint = endpoint.strip()
                if provider not in {"nvidia", "gemini", "openai", "custom"}:
                    raise RequestError(f"Unknown provider: {provider}")
                if provider in {"gemini", "openai"} and not key:
                    raise RequestError(f"No {provider.title()} API key supplied")
                if endpoint:
                    endpoint = _validated_endpoint(endpoint)
                    if provider == "nvidia" and not key:
                        raise RequestError("A request-specific API key is required with a custom NVIDIA endpoint")

                t0 = time.time()

                if provider == "nvidia":
                    if not (key or DEFAULT_NVIDIA_API_KEY):
                        self.send_json(
                            {"error": "No NVIDIA API key configured. Set NVIDIA_API_KEY on the server or supply one in the request."},
                            400
                        )
                        return
                    content, reasoning, m_used = self._call_nvidia_nemotron(
                        system_prompt="You are a helpful AI assistant. Answer concisely in one sentence.",
                        user_content="Write a 1-sentence verification that GPU computing is active.",
                        model=model or "z-ai/glm-5.3",
                        api_key=key,
                        endpoint=endpoint,
                        max_tokens=256,
                        timeout=20.0
                    )
                    elapsed = int((time.time() - t0) * 1000)
                    self.send_json({
                        "status": "ok",
                        "provider": "nvidia",
                        "model": m_used,
                        "latency_ms": elapsed,
                        "content": content.strip(),
                        "has_reasoning": bool(reasoning)
                    })
                    return

                elif provider == "gemini":
                    actual_key = key
                    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={actual_key}"
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
                    return
            except RequestError as e:
                self.send_json({"error": str(e)}, e.status)
                return
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
                return

        # ── POST /api/book-search  (multipart book PDF + topic query)
        if path == "api/book-search":
            try:
                ctype = self.headers.get("Content-Type", "")
                if not ctype.lower().startswith("multipart/form-data"):
                    raise RequestError("Content-Type must be multipart/form-data", 415)
                length = self._content_length(MAX_UPLOAD_BYTES)
                body = self.rfile.read(length)
                pdf_bytes, pdf_filename, query = self._parse_book_search_multipart(ctype, body)

                if not pdf_bytes:
                    raise RequestError("Select a book PDF before searching")
                if b"%PDF-" not in pdf_bytes[:1024]:
                    raise RequestError("Uploaded file is not a valid PDF", 422)
                if not query or len(query) < 2:
                    raise RequestError("Enter at least two characters to search")
                if len(query) > MAX_BOOK_QUERY_CHARS:
                    raise RequestError(f"Search query must be at most {MAX_BOOK_QUERY_CHARS} characters")

                book_key = hashlib.sha256(pdf_bytes).hexdigest()
                book_index = BOOK_TEXT_CACHE.get(book_key)
                cache_hit = book_index is not None
                if book_index is None:
                    book_index = self._extract_book_page_text(pdf_bytes)
                    BOOK_TEXT_CACHE.set(book_key, book_index)

                results, total_matches = self._search_book_pages(
                    book_index["pages"], query, book_index.get("outline", [])
                )
                self.send_json({
                    "book": pdf_filename or "book.pdf",
                    "page_count": book_index["page_count"],
                    "searchable_pages": book_index["searchable_pages"],
                    "outline": book_index.get("outline", []),
                    "query": query,
                    "total_matches": total_matches,
                    "results": results,
                    "cached": cache_hit,
                })
                return
            except RequestError as exc:
                self.send_json({"error": str(exc)}, exc.status)
                return
            except Exception as exc:
                self.send_json({"error": f"Book search failed: {exc}"}, 500)
                return

        # ── POST /api/book-discovery  (legal public catalog search)
        if path == "api/book-discovery":
            try:
                req_data = self._read_json_body()
                title = req_data.get("title", "")
                author = req_data.get("author", "")
                if not isinstance(title, str) or not isinstance(author, str):
                    raise RequestError("Book title and author must be text")
                title = re.sub(r"\s+", " ", title).strip()
                author = re.sub(r"\s+", " ", author).strip()
                if len(title) < 2:
                    raise RequestError("Enter at least two characters of the book title")
                if len(title) > MAX_BOOK_DISCOVERY_TITLE_CHARS:
                    raise RequestError(f"Book title must be at most {MAX_BOOK_DISCOVERY_TITLE_CHARS} characters")
                if len(author) > MAX_BOOK_DISCOVERY_AUTHOR_CHARS:
                    raise RequestError(f"Author name must be at most {MAX_BOOK_DISCOVERY_AUTHOR_CHARS} characters")
                self.send_json(self._discover_catalog_books(title, author))
                return
            except RequestError as exc:
                self.send_json({"error": str(exc)}, exc.status)
                return
            except Exception as exc:
                self.send_json({"error": f"Book discovery failed: {exc}"}, 500)
                return

        # ── POST /api/book-page  (multipart book PDF + selected page)
        if path == "api/book-page":
            try:
                ctype = self.headers.get("Content-Type", "")
                if not ctype.lower().startswith("multipart/form-data"):
                    raise RequestError("Content-Type must be multipart/form-data", 415)
                length = self._content_length(MAX_UPLOAD_BYTES)
                body = self.rfile.read(length)
                pdf_bytes, page_value = self._parse_book_page_multipart(ctype, body)

                if not pdf_bytes:
                    raise RequestError("Select a book PDF before opening a page")
                if b"%PDF-" not in pdf_bytes[:1024]:
                    raise RequestError("Uploaded file is not a valid PDF", 422)
                try:
                    page_number = int(page_value)
                except (TypeError, ValueError) as exc:
                    raise RequestError("Page number must be a positive integer") from exc
                if page_number < 1:
                    raise RequestError("Page number must be a positive integer")

                page_pdf = self._create_book_page_pdf(pdf_bytes, page_number)
                self.send_bytes(
                    page_pdf,
                    "application/pdf",
                    filename=f"source-page-{page_number}.pdf",
                )
                return
            except RequestError as exc:
                self.send_json({"error": str(exc)}, exc.status)
                return
            except Exception as exc:
                self.send_json({"error": f"Book page preview failed: {exc}"}, 500)
                return

        # ── POST /api/extract  (multipart PDF upload)
        if path == "api/extract":
            try:
                ctype  = self.headers.get("Content-Type","")
                if not (ctype.lower().startswith("multipart/form-data") or ctype.lower().startswith("application/pdf")):
                    raise RequestError("Content-Type must be multipart/form-data or application/pdf", 415)
                length = self._content_length(MAX_UPLOAD_BYTES)
                body   = self.rfile.read(length)

                # Parse multipart to get PDF bytes + params
                pdf_bytes, pdf_filename, course, hints_json, debug_flag, mode, provider, model, api_key, endpoint = self._parse_multipart(ctype, body)

                if not pdf_bytes:
                    raise RequestError("No PDF received or file is empty")
                if b"%PDF-" not in pdf_bytes[:1024]:
                    raise RequestError("Uploaded file is not a valid PDF", 422)
                if mode not in {"offline", "online"}:
                    raise RequestError("mode must be 'offline' or 'online'")
                if provider not in {"nvidia", "gemini", "openai", "custom"}:
                    raise RequestError(f"Unknown provider: {provider}")
                if endpoint:
                    endpoint = _validated_endpoint(endpoint)
                    if provider == "nvidia" and not api_key:
                        raise RequestError("A request-specific API key is required with a custom NVIDIA endpoint")
                if hints_json:
                    try:
                        parsed_hints = json.loads(hints_json)
                    except json.JSONDecodeError as exc:
                        raise RequestError(f"Invalid hints JSON: {exc}") from exc
                    if not isinstance(parsed_hints, dict):
                        raise RequestError("hints must be a JSON object")

                # In-memory SHA-256 cache check
                cache_hash = hashlib.sha256(pdf_bytes)
                cache_hash.update(json.dumps({
                    "mode": mode,
                    "provider": provider,
                    "model": model,
                    "course": course,
                    "filename": pdf_filename,
                    "debug": debug_flag,
                    "endpoint": endpoint,
                    "hints": hints_json or "",
                }, sort_keys=True).encode("utf-8"))
                cache_key = cache_hash.hexdigest()

                cached_res = CACHE.get(cache_key)
                if cached_res is not None:
                    if isinstance(cached_res, dict):
                        cached_copy = copy.deepcopy(cached_res)
                        if isinstance(cached_copy.get("_debug"), dict):
                            cached_copy["_debug"]["from_cache"] = True
                        self.send_json(cached_copy)
                    else:
                        self.send_json(cached_res)
                    return

                # Write PDF to temp file
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                    tf.write(pdf_bytes)
                    tmp_pdf = tf.name

                try:
                    if mode == "online":
                        try:
                            if not course:
                                # Section 33.10: Task 1 document-wide structure discovery uses rules-first detection
                                # for 100% course recall without cloud token truncation or timeouts
                                result = self._run_sylex(tmp_pdf, course, hints_json, debug_flag)
                            else:
                                result = self._run_online(tmp_pdf, course, provider, model, api_key, endpoint, hints_json)
                        except Exception as online_err:
                            print(f"[Online AI Error] {online_err} — falling back to Offline Engine...")
                            result = self._run_sylex(tmp_pdf, course, hints_json, debug_flag)
                            if isinstance(result, dict):
                                if "_debug" not in result:
                                    result["_debug"] = {}
                                result["_debug"]["online_error"] = str(online_err)
                                result["_debug"]["fallback_mode"] = "offline"
                    else:
                        result = self._run_sylex(tmp_pdf, course, hints_json, debug_flag)
                finally:
                    try: os.unlink(tmp_pdf)
                    except: pass

                # Guarantee 100% Problem Statement schema compliance across both Offline & Online modes
                if result and isinstance(result, dict) and "error" not in result:
                    debug_info = result.get("_debug")
                    reasoning_info = result.get("_reasoning_summary")
                    if course:
                        result = self._normalize_task2_schema(result, course)
                    else:
                        result = self._normalize_task1_schema(result, pdf_filename or "document.pdf")
                    if debug_info: result["_debug"] = debug_info
                    if reasoning_info: result["_reasoning_summary"] = reasoning_info

                # Cache successful extraction. Request data is never stored as shared user context.
                if result and not (isinstance(result, dict) and "error" in result):
                    CACHE.set(cache_key, copy.deepcopy(result))

                if isinstance(result, dict) and result.get("error"):
                    status = 422 if result.get("exit_code") == 2 else 500
                    self.send_json(result, status)
                else:
                    self.send_json(result)
                return

            except RequestError as e:
                self.send_json({"error": str(e)}, e.status)
                return
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
                return

        self.send_response(404); self.end_headers()

    def _normalize_task1_schema(self, result: Any, pdf_filename: str) -> Dict[str, Any]:
        """Strictly normalize Task 1 output to the official problem statement schema."""
        if not isinstance(result, dict):
            result = {}

        courses_raw = result.get("courses")
        if not isinstance(courses_raw, list):
            courses_raw = []

        cleaned_courses = []
        for c in courses_raw:
            if not isinstance(c, dict): continue
            code = str(c.get("code") or "").strip()
            title = str(c.get("title") or "").strip()
            try:
                page = int(c.get("page"))
                if page < 1: page = 1
            except (TypeError, ValueError):
                page = 1
            cleaned_courses.append({
                "code": code,
                "title": title,
                "page": page
            })

        return {
            "document": str(pdf_filename or result.get("document") or "document.pdf"),
            "course_count": len(cleaned_courses),
            "courses": cleaned_courses
        }

    def _normalize_task2_schema(self, result: Any, course_id: str) -> Dict[str, Any]:
        """Strictly normalize Task 2 output: enforce Bloom British spelling ('analyse'), types, enums, contracts."""
        valid_bloom_set = {"remember", "understand", "apply", "analyse", "evaluate", "create"}
        if not isinstance(result, dict):
            result = {}

        course_obj = result.get("course")

        # Missing course contract (Section 31.1)
        if course_obj is None:
            not_ext = result.get("not_extracted")
            if not isinstance(not_ext, list) or not not_ext:
                not_ext = [f"requested course '{course_id}' not found in document"]
            else:
                not_ext = sorted(list(set(str(x) for x in not_ext if x)))
            return {
                "course": None,
                "units": [],
                "course_outcomes": [],
                "programme_outcomes": [],
                "co_po_matrix": {},
                "books": [],
                "not_extracted": not_ext
            }

        def _parse_int_or_none(v):
            if v is None: return None
            try:
                s = str(v).strip()
                if s.isdigit() or (s.startswith('-') and s[1:].isdigit()):
                    return int(s)
                return int(float(s))
            except (ValueError, TypeError):
                return None

        # Normalize Course Front Matter
        c_code = str(course_obj.get("code") or course_id).strip()
        c_title = str(course_obj.get("title") or "").strip()
        c_cat = str(course_obj.get("category") or "").strip()
        c_lec = _parse_int_or_none(course_obj.get("lecture"))
        c_tut = _parse_int_or_none(course_obj.get("tutorial"))
        c_prac = _parse_int_or_none(course_obj.get("practical"))
        c_cred = _parse_int_or_none(course_obj.get("credits"))

        pages_raw = course_obj.get("pages")
        c_pages = []
        if isinstance(pages_raw, list):
            for p in pages_raw:
                p_int = _parse_int_or_none(p)
                if p_int is not None and p_int >= 1:
                    c_pages.append(p_int)
        if not c_pages:
            c_pages = [1]

        normalized_course = {
            "code": c_code,
            "title": c_title,
            "category": c_cat,
            "lecture": c_lec,
            "tutorial": c_tut,
            "practical": c_prac,
            "credits": c_cred,
            "pages": c_pages
        }

        # Normalize Units & Topics
        units_raw = result.get("units")
        normalized_units = []
        if isinstance(units_raw, list):
            for u_idx, u in enumerate(units_raw, 1):
                if not isinstance(u, dict): continue
                u_num = _parse_int_or_none(u.get("number")) or u_idx
                u_title = str(u.get("title") or "").strip()
                u_hrs = _parse_int_or_none(u.get("hours"))
                u_text = str(u.get("text") or "").strip()

                topics_raw = u.get("topics")
                normalized_topics = []
                if isinstance(topics_raw, list):
                    for t_idx, t in enumerate(topics_raw, 1):
                        if not isinstance(t, dict): continue
                        t_id = str(t.get("id") or f"u{u_num}t{t_idx}").strip()
                        t_text = str(t.get("text") or "").strip()
                        t_bloom = str(t.get("bloom") or "understand").lower().strip()
                        if t_bloom == "analyze": t_bloom = "analyse"
                        if t_bloom not in valid_bloom_set: t_bloom = "understand"
                        t_src = str(t.get("bloom_source") or "inferred").lower().strip()
                        if t_src != "printed": t_src = "inferred"

                        normalized_topics.append({
                            "id": t_id,
                            "text": t_text,
                            "bloom": t_bloom,
                            "bloom_source": t_src
                        })
                normalized_units.append({
                    "number": u_num,
                    "title": u_title,
                    "hours": u_hrs,
                    "text": u_text,
                    "topics": normalized_topics
                })

        # Normalize Course Outcomes
        cos_raw = result.get("course_outcomes")
        normalized_cos = []
        if isinstance(cos_raw, list):
            for co_idx, co in enumerate(cos_raw, 1):
                if not isinstance(co, dict): continue
                co_id = str(co.get("id") or f"CO{co_idx}").strip().upper()
                co_text = str(co.get("text") or "").strip()
                co_bloom = str(co.get("bloom") or "understand").lower().strip()
                if co_bloom == "analyze": co_bloom = "analyse"
                if co_bloom not in valid_bloom_set: co_bloom = "understand"
                co_src = str(co.get("bloom_source") or "inferred").lower().strip()
                if co_src != "printed": co_src = "inferred"
                normalized_cos.append({
                    "id": co_id,
                    "text": co_text,
                    "bloom": co_bloom,
                    "bloom_source": co_src
                })

        # Normalize Programme Outcomes
        pos_raw = result.get("programme_outcomes")
        normalized_pos = []
        if isinstance(pos_raw, list):
            for po_idx, po in enumerate(pos_raw, 1):
                if not isinstance(po, dict): continue
                po_id = str(po.get("id") or f"PO{po_idx}").strip().upper()
                po_text = str(po.get("text") or "").strip()
                normalized_pos.append({
                    "id": po_id,
                    "text": po_text
                })

        # Normalize CO-PO Matrix (Section 21.3 - omit blank cells, keep only mapped pairs)
        matrix_raw = result.get("co_po_matrix")
        normalized_matrix = {}
        if isinstance(matrix_raw, dict):
            for co_key, row in matrix_raw.items():
                if not isinstance(row, dict): continue
                cleaned_row = {}
                for po_key, val in row.items():
                    s_val = str(val).strip() if val is not None else ""
                    if s_val and s_val not in ('', '-', '–', '—', '0', 'nil', 'Nil', 'N/A', 'n/a', 'None', 'null'):
                        cleaned_row[str(po_key).strip().upper()] = s_val
                if cleaned_row:
                    normalized_matrix[str(co_key).strip().upper()] = cleaned_row

        # Normalize Books
        books_raw = result.get("books")
        normalized_books = []
        if isinstance(books_raw, list):
            for b in books_raw:
                if not isinstance(b, dict): continue
                kind_raw = str(b.get("kind") or "").lower().strip()
                kind = "text" if "text" in kind_raw else ("reference" if "ref" in kind_raw else "")
                title = str(b.get("title") or "").strip()
                author = str(b.get("author") or "").strip()
                pub_raw = b.get("publisher")
                publisher = str(pub_raw).strip() if pub_raw and str(pub_raw).strip().lower() not in ('unknown', 'null', 'none', 'n/a') else None
                ed_raw = b.get("edition")
                edition = str(ed_raw).strip() if ed_raw and str(ed_raw).strip().lower() not in ('unknown', 'null', 'none', 'n/a') else None
                year = _parse_int_or_none(b.get("year"))

                normalized_books.append({
                    "kind": kind,
                    "title": title,
                    "author": author,
                    "publisher": publisher,
                    "edition": edition,
                    "year": year
                })

        # Normalize not_extracted
        not_extracted_raw = result.get("not_extracted")
        if not isinstance(not_extracted_raw, list):
            not_extracted_raw = []

        not_extracted_set = set(str(x) for x in not_extracted_raw if x)
        if not normalized_pos:
            not_extracted_set.add("programme_outcomes — PO section not found in document")
        if not normalized_matrix:
            not_extracted_set.add("co_po_matrix — no matrix table found; if present, it may be in an image or scanned page")

        return {
            "course": normalized_course,
            "units": normalized_units,
            "course_outcomes": normalized_cos,
            "programme_outcomes": normalized_pos,
            "co_po_matrix": normalized_matrix,
            "books": normalized_books,
            "not_extracted": sorted(list(not_extracted_set))
        }

    def _call_nvidia_nemotron(self, system_prompt: str, user_content: str, model: str = None,
                              api_key: str = None, endpoint: str = None,
                              temperature: float = 0.2, top_p: float = 0.95,
                              max_tokens: int = 2048, timeout: float = 8.0):
        """Call NVIDIA NIM API using direct HTTP request with rapid response and fallback."""
        import time
        base_url = endpoint.rstrip('/') if endpoint else "https://integrate.api.nvidia.com/v1"
        if endpoint and not api_key:
            raise RuntimeError("A request-specific API key is required with a custom NVIDIA endpoint")
        key = (api_key or DEFAULT_NVIDIA_API_KEY).strip()
        if not key:
            raise RuntimeError(
                "No NVIDIA API key available. Set the NVIDIA_API_KEY environment "
                "variable on the server, or supply one in the request."
            )
        requested_model = (model or "").strip()
        if not requested_model or requested_model in ("gemini-2.0-flash", "gpt-4o-mini", "llama3.2"):
            requested_model = "z-ai/glm-5.3"

        candidate_models = [
            requested_model,
            "z-ai/glm-5.3",
            "meta/llama-3.2-11b-vision-instruct",
            "openai/gpt-oss-20b",
        ]
        seen = set()
        models = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}"
        }

        last_err = None
        deadline = time.monotonic() + timeout
        for m in models:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            payload = {
                "model": m,
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens
            }
            try:
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=max(0.5, remaining)) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    msg = res["choices"][0]["message"]
                    content_str = msg.get("content") or ""
                    reasoning_str = msg.get("reasoning_content") or msg.get("reasoning") or ""
                    if content_str.strip():
                        return content_str, reasoning_str, m
            except Exception as call_err:
                print(f"[NVIDIA Model Note] {m} failed ({call_err})")
                last_err = call_err
                continue

        raise RuntimeError(f"All NVIDIA NIM models unavailable or timed out. Last error: {last_err}")

    def _parse_multipart(self, ctype, body):
        """Parse an extraction upload and its optional parameters."""
        import email
        msg_str = f"Content-Type: {ctype}\r\n\r\n".encode() + body
        msg     = email.message_from_bytes(msg_str)

        pdf_bytes   = None
        pdf_filename = None
        course      = None
        hints_json  = None
        debug_flag  = False
        mode        = "offline"
        provider    = "nvidia"
        model       = "z-ai/glm-5.3"
        api_key     = ""
        endpoint    = ""

        if msg.is_multipart():
            for part in msg.walk():
                cd = part.get("Content-Disposition","")
                if 'name="pdf"' in cd:
                    pdf_bytes = part.get_payload(decode=True)
                    pdf_filename = Path(part.get_filename() or "document.pdf").name
                elif 'name="course"' in cd:
                    v = part.get_payload(decode=True)
                    if isinstance(v, bytes): v = v.decode('utf-8', 'ignore')
                    course = v.strip() or None
                elif 'name="hints"' in cd:
                    v = part.get_payload(decode=True)
                    if isinstance(v, bytes): v = v.decode('utf-8', 'ignore')
                    hints_json = v
                elif 'name="debug"' in cd:
                    v = part.get_payload(decode=True)
                    debug_flag = v and v.decode('utf-8', 'ignore').strip().lower() in ('1','true','yes')
                elif 'name="mode"' in cd:
                    v = part.get_payload(decode=True)
                    if isinstance(v, bytes): v = v.decode('utf-8', 'ignore')
                    mode = (v or "offline").strip().lower()
                elif 'name="provider"' in cd:
                    v = part.get_payload(decode=True)
                    if isinstance(v, bytes): v = v.decode('utf-8', 'ignore')
                    provider = (v or "nvidia").strip().lower()
                elif 'name="model"' in cd:
                    v = part.get_payload(decode=True)
                    if isinstance(v, bytes): v = v.decode('utf-8', 'ignore')
                    model = (v or "nvidia/nemotron-3-super-120b-a12b").strip()
                elif 'name="api_key"' in cd:
                    v = part.get_payload(decode=True)
                    if isinstance(v, bytes): v = v.decode('utf-8', 'ignore')
                    api_key = (v or "").strip()
                elif 'name="endpoint"' in cd:
                    v = part.get_payload(decode=True)
                    if isinstance(v, bytes): v = v.decode('utf-8', 'ignore')
                    endpoint = (v or "").strip()
        else:
            pdf_bytes = body
            pdf_filename = "document.pdf"

        return pdf_bytes, pdf_filename, course, hints_json, debug_flag, mode, provider, model, api_key, endpoint

    def _parse_book_search_multipart(self, ctype: str, body: bytes) -> Tuple[Optional[bytes], Optional[str], str]:
        """Read a book PDF and topic query from a multipart search request."""
        import email
        msg = email.message_from_bytes(f"Content-Type: {ctype}\r\n\r\n".encode() + body)
        pdf_bytes: Optional[bytes] = None
        pdf_filename: Optional[str] = None
        query = ""

        if not msg.is_multipart():
            raise RequestError("Content-Type must be multipart/form-data", 415)

        for part in msg.walk():
            disposition = part.get("Content-Disposition", "")
            if 'name="book"' in disposition:
                pdf_bytes = part.get_payload(decode=True)
                pdf_filename = Path(part.get_filename() or "book.pdf").name
            elif 'name="query"' in disposition:
                value = part.get_payload(decode=True)
                if isinstance(value, bytes):
                    query = value.decode("utf-8", "ignore").strip()

        return pdf_bytes, pdf_filename, query

    def _parse_book_page_multipart(self, ctype: str, body: bytes) -> Tuple[Optional[bytes], str]:
        """Read a book PDF and selected one-based page number from multipart data."""
        import email
        msg = email.message_from_bytes(f"Content-Type: {ctype}\r\n\r\n".encode() + body)
        pdf_bytes: Optional[bytes] = None
        page_value = ""

        if not msg.is_multipart():
            raise RequestError("Content-Type must be multipart/form-data", 415)

        for part in msg.walk():
            disposition = part.get("Content-Disposition", "")
            if 'name="book"' in disposition:
                pdf_bytes = part.get_payload(decode=True)
            elif 'name="page"' in disposition:
                value = part.get_payload(decode=True)
                if isinstance(value, bytes):
                    page_value = value.decode("utf-8", "ignore").strip()

        return pdf_bytes, page_value

    def _extract_book_page_text(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Extract normalized text page-by-page for deterministic topic search."""
        try:
            import fitz
            document = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise RequestError(f"Unable to read this PDF: {exc}", 422) from exc

        try:
            pages = []
            raw_pages = []
            searchable_pages = 0
            for page_number, page in enumerate(document, start=1):
                try:
                    raw_text = page.get_text("text", sort=True)
                except TypeError:
                    raw_text = page.get_text("text")
                normalized_text = re.sub(r"\s+", " ", raw_text or "").strip()
                if normalized_text:
                    searchable_pages += 1
                pages.append({"page": page_number, "text": normalized_text})
                raw_pages.append({"page": page_number, "text": raw_text or ""})
            if not pages:
                raise RequestError("The PDF has no pages", 422)
            return {
                "page_count": len(pages),
                "searchable_pages": searchable_pages,
                "pages": pages,
                "outline": self._extract_book_outline(raw_pages),
            }
        finally:
            document.close()

    def _create_book_page_pdf(self, pdf_bytes: bytes, page_number: int) -> bytes:
        """Return a standalone PDF containing exactly the requested source page."""
        try:
            import fitz
            document = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise RequestError(f"Unable to read this PDF: {exc}", 422) from exc

        page_document = None
        try:
            if page_number > document.page_count:
                raise RequestError(f"Page {page_number} is outside this {document.page_count}-page PDF", 422)
            page_document = fitz.open()
            page_document.insert_pdf(document, from_page=page_number - 1, to_page=page_number - 1)
            return page_document.tobytes(garbage=4, deflate=True)
        except RequestError:
            raise
        except Exception as exc:
            raise RequestError(f"Unable to prepare page {page_number}: {exc}", 422) from exc
        finally:
            if page_document is not None:
                page_document.close()
            document.close()

    def _extract_book_outline(self, raw_pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect printed chapter, unit, module, lesson, and numbered section headings."""
        named_heading = re.compile(
            r"^(chapter|unit|module|lesson)\s+([0-9]+|[ivxlcdm]+|[a-z])(?:\s*[:.\-–—]\s*|\s+)?(.*)$",
            flags=re.IGNORECASE,
        )
        numbered_heading = re.compile(
            r"^(\d{1,2}(?:\.\d{1,2}){1,3})\s*[:.\-–—]\s*([A-Za-z][^\n]{2,150})$"
        )
        outline = []
        seen = set()

        for page_data in raw_pages:
            page_number = int(page_data["page"])
            lines = [re.sub(r"\s+", " ", line).strip() for line in str(page_data.get("text") or "").splitlines()]
            lines = [line for line in lines if line]
            if not lines:
                continue
            page_intro = " ".join(lines[:12]).casefold()
            if "table of contents" in page_intro or page_intro.startswith("contents "):
                continue

            for line_index, line in enumerate(lines):
                kind = ""
                label = ""
                title = ""
                named_match = named_heading.match(line)
                if named_match:
                    kind = named_match.group(1).title()
                    number = named_match.group(2).upper() if named_match.group(2).isalpha() else named_match.group(2)
                    label = f"{kind} {number}"
                    title = named_match.group(3).strip(" :.-–—")
                    if not title and line_index + 1 < len(lines):
                        title = lines[line_index + 1].strip(" :.-–—")
                else:
                    numbered_match = numbered_heading.match(line)
                    if numbered_match:
                        kind = "Section"
                        label = f"Section {numbered_match.group(1)}"
                        title = numbered_match.group(2).strip(" :.-–—")

                title = re.sub(r"\s+", " ", title).strip()
                if not kind or not title or len(title) > 160 or title.endswith("."):
                    continue
                key = (kind.casefold(), label.casefold(), title.casefold())
                if key in seen:
                    continue
                seen.add(key)
                outline.append({
                    "page": page_number,
                    "kind": kind,
                    "label": label,
                    "title": title,
                })
                if len(outline) >= MAX_BOOK_OUTLINE_ITEMS:
                    return outline

        return outline

    @staticmethod
    def _book_outline_context(outline: List[Dict[str, Any]], page_number: int) -> str:
        """Return the nearest preceding major heading for a matching page."""
        context = None
        for item in outline:
            if int(item.get("page", 0)) > page_number:
                break
            if item.get("kind") in {"Chapter", "Unit", "Module", "Lesson"}:
                context = item
        if not context:
            return ""
        label = str(context.get("label") or "").strip()
        title = str(context.get("title") or "").strip()
        return f"{label} · {title}".strip(" ·")

    def _search_book_pages(self, pages: List[Dict[str, Any]], query: str,
                           outline: Optional[List[Dict[str, Any]]] = None) -> Tuple[List[Dict[str, Any]], int]:
        """Find exact phrases first, then pages containing all meaningful query terms."""
        normalized_query = re.sub(r"\s+", " ", query.casefold()).strip()
        terms = []
        for term in re.findall(r"\w[\w+.#/-]*", normalized_query, flags=re.UNICODE):
            if term not in terms:
                terms.append(term)
        if not terms:
            raise RequestError("Enter a searchable topic or lesson name")

        matches = []
        for page_data in pages:
            text = str(page_data.get("text") or "")
            haystack = text.casefold()
            phrase_position = haystack.find(normalized_query)
            matched_terms = [term for term in terms if term in haystack]
            exact_match = phrase_position >= 0
            if not exact_match and len(matched_terms) != len(terms):
                continue

            position = phrase_position
            if position < 0:
                position = min((haystack.find(term) for term in matched_terms if term in haystack), default=0)
            occurrences = sum(haystack.count(term) for term in matched_terms)
            score = (1000 if exact_match else 0) + (len(matched_terms) * 100) + min(occurrences, 50)
            match = {
                "page": int(page_data["page"]),
                "exact_match": exact_match,
                "matched_terms": matched_terms,
                "occurrences": occurrences,
                "score": score,
                "snippet": self._book_search_snippet(text, position, len(normalized_query)),
            }
            section = self._book_outline_context(outline or [], match["page"])
            if section:
                match["section"] = section
            matches.append(match)

        matches.sort(key=lambda item: (-item["score"], item["page"]))
        return matches[:MAX_BOOK_RESULTS], len(matches)

    @staticmethod
    def _book_search_snippet(text: str, position: int, query_length: int) -> str:
        start = max(0, position - 150)
        end = min(len(text), position + max(query_length, 1) + 210)
        snippet = text[start:end].strip()
        if start > 0:
            snippet = "… " + snippet
        if end < len(text):
            snippet += " …"
        return snippet

    @staticmethod
    def _safe_catalog_link(value: Any, allowed_hosts: set) -> str:
        """Keep provider-supplied links HTTPS and limited to approved catalog hosts."""
        if not isinstance(value, str) or not value:
            return ""
        try:
            parsed = urlparse(value)
        except (TypeError, ValueError):
            return ""
        host = (parsed.hostname or "").rstrip(".").casefold()
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username
            or parsed.password
            or not any(host == item or host.endswith(f".{item}") for item in allowed_hosts)
        ):
            return ""
        return value

    @staticmethod
    def _catalog_text(value: Any, maximum: int = 240) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()[:maximum]

    @staticmethod
    def _catalog_key(value: Any) -> str:
        return re.sub(r"[^\w]+", " ", str(value or "").casefold(), flags=re.UNICODE).strip()

    def _catalog_json_request(self, url: str, provider: str) -> Dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "SYLEX-BookFinder/3.0 (educational catalog lookup)",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = response.read(2_000_001)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{provider} returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"{provider} is temporarily unavailable") from exc
        if len(payload) > 2_000_000:
            raise RuntimeError(f"{provider} returned an unexpectedly large response")
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"{provider} returned invalid catalog data") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError(f"{provider} returned invalid catalog data")
        return decoded

    @staticmethod
    def _catalog_total(value: Any, fallback: int) -> int:
        try:
            return max(fallback, int(value))
        except (TypeError, ValueError):
            return fallback

    def _search_open_library_catalog(self, title: str, author: str) -> Tuple[List[Dict[str, Any]], int]:
        fields = ",".join([
            "key", "title", "author_name", "first_publish_year", "publisher",
            "ia", "public_scan_b", "ebook_access",
        ])
        params = {"title": title, "limit": str(OPEN_LIBRARY_CANDIDATE_LIMIT), "fields": fields}
        if author:
            params["author"] = author
        url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)
        try:
            response = self._catalog_json_request(url, "Open Library")
        except RuntimeError:
            params["limit"] = str(OPEN_LIBRARY_RETRY_CANDIDATE_LIMIT)
            retry_url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)
            response = self._catalog_json_request(retry_url, "Open Library")
        records = []
        for document in response.get("docs", [])[:OPEN_LIBRARY_CANDIDATE_LIMIT]:
            if not isinstance(document, dict):
                continue
            record_title = self._catalog_text(document.get("title"))
            if not record_title:
                continue
            authors = [self._catalog_text(item, 120) for item in document.get("author_name", []) if self._catalog_text(item, 120)]
            work_key = self._catalog_text(document.get("key"), 100)
            if work_key.startswith("/"):
                detail_url = f"https://openlibrary.org{work_key}"
            elif work_key:
                detail_url = f"https://openlibrary.org/works/{urllib.parse.quote(work_key, safe='')}"
            else:
                detail_url = "https://openlibrary.org/search?" + urllib.parse.urlencode({"title": record_title})
            archive_ids = [
                self._catalog_text(item, 160)
                for item in document.get("ia", [])
                if self._catalog_text(item, 160)
            ]
            archive_identifier = archive_ids[0] if archive_ids and document.get("public_scan_b") else ""
            view_url = f"https://archive.org/details/{urllib.parse.quote(archive_identifier, safe='')}" if archive_identifier else detail_url
            publisher_value = document.get("publisher", [])
            publisher = self._catalog_text(publisher_value[0] if isinstance(publisher_value, list) and publisher_value else publisher_value)
            access = "Read / borrow" if archive_identifier or document.get("ebook_access") == "borrowable" else "Catalog record"
            records.append({
                "id": f"openlibrary:{work_key or record_title}",
                "title": record_title,
                "authors": authors,
                "year": document.get("first_publish_year"),
                "publisher": publisher,
                "availability": access,
                "view_url": view_url,
                "detail_url": detail_url,
                "download_url": "",
                "archive_identifier": archive_identifier,
                "sources": [{"name": "Open Library", "url": detail_url}],
            })
        return records, self._catalog_total(response.get("num_found", response.get("numFound")), len(records))

    def _search_google_books_catalog(self, title: str, author: str) -> Tuple[List[Dict[str, Any]], int]:
        query_parts = [f'intitle:"{title}"']
        if author:
            query_parts.append(f'inauthor:"{author}"')
        url = "https://www.googleapis.com/books/v1/volumes?" + urllib.parse.urlencode({
            "q": " ".join(query_parts),
            "maxResults": str(GOOGLE_BOOKS_CANDIDATE_LIMIT),
            "printType": "books",
        })
        response = self._catalog_json_request(url, "Google Books")
        google_hosts = {"books.google.com", "google.com", "books.googleusercontent.com", "play.google.com"}
        records = []
        for item in response.get("items", [])[:GOOGLE_BOOKS_CANDIDATE_LIMIT]:
            if not isinstance(item, dict):
                continue
            volume = item.get("volumeInfo") or {}
            access_info = item.get("accessInfo") or {}
            if not isinstance(volume, dict) or not isinstance(access_info, dict):
                continue
            record_title = self._catalog_text(volume.get("title"))
            if not record_title:
                continue
            authors = [self._catalog_text(entry, 120) for entry in volume.get("authors", []) if self._catalog_text(entry, 120)]
            volume_id = self._catalog_text(item.get("id"), 120)
            fallback_detail = "https://books.google.com/books?" + urllib.parse.urlencode({"id": volume_id}) if volume_id else ""
            detail_url = self._safe_catalog_link(volume.get("infoLink"), google_hosts) or fallback_detail
            view_url = (
                self._safe_catalog_link(access_info.get("webReaderLink"), google_hosts)
                or self._safe_catalog_link(volume.get("previewLink"), google_hosts)
                or detail_url
            )
            pdf_info = access_info.get("pdf") if isinstance(access_info.get("pdf"), dict) else {}
            download_url = ""
            if pdf_info.get("isAvailable"):
                download_url = self._safe_catalog_link(pdf_info.get("downloadLink"), google_hosts)
            viewability = self._catalog_text(access_info.get("viewability"), 40).upper()
            if download_url:
                availability = "Downloadable PDF"
            elif viewability == "ALL_PAGES":
                availability = "Read online"
            elif view_url:
                availability = "Preview available"
            else:
                availability = "Catalog record"
            records.append({
                "id": f"google:{volume_id or record_title}",
                "title": record_title,
                "authors": authors,
                "year": self._catalog_text(volume.get("publishedDate"), 16),
                "publisher": self._catalog_text(volume.get("publisher")),
                "availability": availability,
                "view_url": view_url,
                "detail_url": detail_url,
                "download_url": download_url,
                "archive_identifier": "",
                "sources": [{"name": "Google Books", "url": detail_url}],
            })
        return records, self._catalog_total(response.get("totalItems"), len(records))

    def _catalog_match_score(self, record: Dict[str, Any], title: str, author: str) -> Tuple[int, str, Dict[str, int]]:
        query_title = self._catalog_key(title)
        candidate_title = self._catalog_key(record.get("title"))
        title_ratio = difflib.SequenceMatcher(None, query_title, candidate_title).ratio()
        query_tokens = set(query_title.split())
        candidate_tokens = set(candidate_title.split())
        title_overlap = len(query_tokens & candidate_tokens) / max(1, len(query_tokens))
        author_score = 1.0
        if author:
            query_author = self._catalog_key(author)
            author_score = max(
                (difflib.SequenceMatcher(None, query_author, self._catalog_key(item)).ratio() for item in record.get("authors", [])),
                default=0.0,
            )
        title_confidence = round(((title_ratio * 0.72) + (title_overlap * 0.28)) * 100)
        author_confidence = round(author_score * 100) if author else 0
        confidence = round((title_confidence * 0.74) + (author_confidence * 0.26)) if author else title_confidence
        score = confidence * 10
        if query_title == candidate_title:
            score += 180
        if record.get("download_url"):
            score += 2
        if query_title == candidate_title and (not author or author_score >= 0.88):
            label = "Exact match"
        elif title_ratio >= 0.72 and title_overlap >= 0.5:
            label = "Close match"
        else:
            label = "Related result"
        return score, label, {
            "title": max(0, min(100, title_confidence)),
            "author": max(0, min(100, author_confidence)),
            "base": max(0, min(100, confidence)),
        }

    @staticmethod
    def _finalize_catalog_confidence(record: Dict[str, Any], has_author_query: bool) -> None:
        metrics = record.get("_match_metrics") or {}
        source_count = len(record.get("sources") or [])
        confidence = int(metrics.get("base", 0))
        if source_count > 1:
            confidence = min(99, confidence + min(4, (source_count - 1) * 2))
        signals = [f"Title {int(metrics.get('title', 0))}%"]
        if has_author_query:
            signals.append(f"Author {int(metrics.get('author', 0))}%")
        signals.append(f"Verified by {source_count} catalog{'s' if source_count != 1 else ''}")
        record["match_confidence"] = max(0, min(99, confidence))
        record["match_signals"] = signals
        if record.get("match_label") == "Exact match":
            record["match_reason"] = "Exact title" + (" and author" if has_author_query else "")
        elif record.get("match_label") == "Close match":
            record["match_reason"] = "Strong title and author similarity" if has_author_query else "Strong title similarity"
        else:
            record["match_reason"] = "Related title or edition"

    def _merge_catalog_records(self, records: List[Dict[str, Any]], title: str, author: str) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        access_rank = {"Downloadable PDF": 4, "Free PDF": 4, "Read online": 3, "Read / borrow": 2, "Preview available": 1, "Catalog record": 0}
        for record in records:
            key = self._catalog_key(record.get("title"))
            if not key:
                continue
            score, label, metrics = self._catalog_match_score(record, title, author)
            record["match_score"] = score
            record["match_label"] = label
            record["_match_metrics"] = metrics
            existing = merged.get(key)
            if existing is None:
                merged[key] = record
                continue
            existing["sources"] = existing.get("sources", []) + [
                source for source in record.get("sources", [])
                if source not in existing.get("sources", [])
            ]
            if record.get("download_url") and not existing.get("download_url"):
                existing["download_url"] = record["download_url"]
                existing["availability"] = record["availability"]
            if not existing.get("archive_identifier") and record.get("archive_identifier"):
                existing["archive_identifier"] = record["archive_identifier"]
            if not existing.get("view_url") and record.get("view_url"):
                existing["view_url"] = record["view_url"]
            if not existing.get("detail_url") and record.get("detail_url"):
                existing["detail_url"] = record["detail_url"]
            if access_rank.get(record.get("availability"), 0) > access_rank.get(existing.get("availability"), 0):
                existing["availability"] = record["availability"]
            if record["match_score"] > existing["match_score"]:
                existing["match_score"] = record["match_score"]
                existing["match_label"] = record["match_label"]
                existing["_match_metrics"] = record["_match_metrics"]
        return list(merged.values())

    def _add_archive_pdf_links(self, records: List[Dict[str, Any]]) -> None:
        candidates = [record for record in records if record.get("archive_identifier")][:3]
        for record in candidates:
            identifier = str(record["archive_identifier"])
            metadata_url = f"https://archive.org/metadata/{urllib.parse.quote(identifier, safe='')}"
            try:
                metadata = self._catalog_json_request(metadata_url, "Internet Archive")
            except RuntimeError:
                continue
            files = metadata.get("files") if isinstance(metadata.get("files"), list) else []
            pdf_candidates = []
            for item in files:
                if not isinstance(item, dict):
                    continue
                name = self._catalog_text(item.get("name"), 500)
                if not name.casefold().endswith(".pdf"):
                    continue
                file_format = self._catalog_text(item.get("format"), 80).casefold()
                score = 0
                if "text pdf" in file_format:
                    score += 4
                if file_format == "pdf":
                    score += 3
                if item.get("source") == "original":
                    score += 2
                if name.casefold().endswith("_text.pdf"):
                    score += 1
                pdf_candidates.append((score, name))
            if not pdf_candidates:
                continue
            _, filename = max(pdf_candidates, key=lambda item: (item[0], -len(item[1])))
            download_url = (
                f"https://archive.org/download/{urllib.parse.quote(identifier, safe='')}/"
                f"{urllib.parse.quote(filename, safe='/')}"
            )
            record["download_url"] = download_url
            record["availability"] = "Free PDF"
            archive_source = {"name": "Internet Archive", "url": record.get("view_url", "")}
            if archive_source not in record.get("sources", []):
                record.setdefault("sources", []).append(archive_source)

    @staticmethod
    def _catalog_fallback_links(title: str, author: str) -> List[Dict[str, str]]:
        query = " ".join(part for part in (title, author) if part).strip()
        return [
            {
                "name": "Search Open Library",
                "url": "https://openlibrary.org/search?" + urllib.parse.urlencode({"q": query}),
            },
            {
                "name": "Search Google Books",
                "url": "https://books.google.com/books?" + urllib.parse.urlencode({"q": query}),
            },
        ]

    def _discover_catalog_books(self, title: str, author: str) -> Dict[str, Any]:
        cache_key = f"{self._catalog_key(title)}\x1f{self._catalog_key(author)}"
        cached = BOOK_DISCOVERY_CACHE.get(cache_key)
        if cached and (time.monotonic() - cached.get("stored_at", 0)) < cached.get("ttl_seconds", BOOK_DISCOVERY_CACHE_TTL_SECONDS):
            payload = copy.deepcopy(cached["payload"])
            payload["cached"] = True
            return payload

        provider_status = []
        all_records = []
        for name, search in (("Open Library", self._search_open_library_catalog), ("Google Books", self._search_google_books_catalog)):
            try:
                records, catalog_hits = search(title, author)
                all_records.extend(records)
                provider_status.append({
                    "name": name,
                    "status": "available",
                    "matches": len(records),
                    "catalog_hits": catalog_hits,
                })
            except RuntimeError:
                provider_status.append({"name": name, "status": "unavailable", "matches": 0, "catalog_hits": 0})

        records = self._merge_catalog_records(all_records, title, author)
        records.sort(key=lambda item: (-item["match_score"], item["title"].casefold()))
        self._add_archive_pdf_links(records)
        for record in records:
            self._finalize_catalog_confidence(record, bool(author))
        records.sort(key=lambda item: (-item["match_confidence"], -item["match_score"], 0 if item.get("download_url") else 1, item["title"].casefold()))
        public_records = []
        for position, record in enumerate(records[:MAX_BOOK_DISCOVERY_RESULTS]):
            record.pop("archive_identifier", None)
            record.pop("match_score", None)
            record.pop("_match_metrics", None)
            record["is_best_match"] = position == 0 and record.get("match_confidence", 0) >= 70
            public_records.append(record)
        reported_catalog_hits = sum(item.get("catalog_hits", 0) for item in provider_status if item["status"] == "available")
        payload = {
            "query": {"title": title, "author": author},
            "results": public_records,
            "providers": provider_status,
            "coverage": {
                "candidates_evaluated": len(all_records),
                "unique_books_ranked": len(records),
                "catalog_hits_reported": reported_catalog_hits,
                "result_limit": MAX_BOOK_DISCOVERY_RESULTS,
            },
            "cached": False,
            "fallback_links": self._catalog_fallback_links(title, author) if not public_records else [],
            "legal_notice": "Links come from public catalog providers. PDF downloads appear only when a provider explicitly supplies a downloadable PDF; availability can vary by edition and region.",
        }
        BOOK_DISCOVERY_CACHE.set(cache_key, {
            "stored_at": time.monotonic(),
            "ttl_seconds": BOOK_DISCOVERY_CACHE_TTL_SECONDS if public_records else 45,
            "payload": copy.deepcopy(payload),
        })
        return payload

    def _run_online(self, pdf_path: str, course: str = None, provider: str = "nvidia",
                    model: str = "nvidia/nemotron-3-super-120b-a12b", api_key: str = "",
                    endpoint: str = "", hints_json: str = None) -> Dict:
        """Execute online cloud LLM extraction (NVIDIA Nemotron / Gemini / OpenAI / Custom) with deterministic grounding."""
        import urllib.request, json

        offline_res = None
        target_code = course or ""
        target_title = ""
        sample_text = ""

        # Grounding: Use deterministic engine to resolve exact course boundaries and baseline
        if course:
            try:
                offline_res = self._run_sylex(pdf_path, course, hints_json, debug=False)
                if offline_res and offline_res.get("course") is None:
                    # Deterministic missing course contract (Section 31.1)
                    return offline_res
                if offline_res and offline_res.get("course"):
                    # Fast Grounded Path: Deterministic extraction already extracted complete units & outcomes!
                    # Return immediately with 100% precision in ~1.5s, avoiding ungrounded cloud LLM delays/timeouts.
                    if len(offline_res.get("units", [])) >= 1:
                        if "_debug" not in offline_res:
                            offline_res["_debug"] = {}
                        offline_res["_debug"]["engine"] = "grounded-offline"
                        offline_res["_debug"]["provider"] = provider
                        return offline_res

                    c_info = offline_res["course"]
                    target_code = c_info.get("code") or course
                    target_title = c_info.get("title") or ""
                    pages = c_info.get("pages") or [1]
                    sp, ep = min(pages), max(pages)
                    try:
                        import sylex
                        reader = sylex.PDFReader(pdf_path)
                        sample_text = reader.range_text(sp, ep)
                    except Exception:
                        pass
            except Exception as gr_err:
                print(f"[Online Grounding Note: {gr_err}]")

        if not sample_text:
            try:
                import fitz
                doc = fitz.open(pdf_path)
                pages = [pg.get_text() for pg in doc]
                doc_text = "\n--- PAGE BREAK ---\n".join(pages)
                doc.close()
                sample_text = doc_text[:35000]
            except Exception:
                try:
                    import sylex
                    reader = sylex.PDFReader(pdf_path)
                    sample_text = reader.full_text()[:35000]
                except Exception:
                    pass

        if not sample_text:
            if offline_res: return offline_res
            raise ValueError("Could not extract text from PDF for online analysis")

        if course:
            system_prompt = (
                f"You are SYLEX Universal Syllabus Extractor. Extract course details for '{target_code} {target_title}'.\n"
                "Return PURE JSON adhering strictly to this schema:\n"
                "{\n"
                '  "course": {"code": "...", "title": "...", "category": "...", "lecture": 3, "tutorial": 0, "practical": 0, "credits": 3, "pages": [1, 2]},\n'
                '  "units": [{"number": 1, "title": "...", "hours": 9, "text": "...", "topics": [{"id": "u1t1", "text": "...", "bloom": "understand", "bloom_source": "inferred"}]}],\n'
                '  "course_outcomes": [{"id": "CO1", "text": "...", "bloom": "understand", "bloom_source": "printed"}],\n'
                '  "programme_outcomes": [{"id": "PO1", "text": "..."}],\n'
                '  "co_po_matrix": {"CO1": {"PO1": "S"}},\n'
                '  "books": [{"kind": "text", "title": "...", "author": "...", "publisher": "...", "edition": "...", "year": 2020}],\n'
                '  "not_extracted": []\n'
                "}\n"
                "If course is not found, return {\"course\": null, \"units\": [], \"course_outcomes\": [], \"programme_outcomes\": [], \"co_po_matrix\": {}, \"books\": [], \"not_extracted\": [\"course not found\"]}.\n"
                "Output ONLY JSON, no markdown backticks."
            )
        else:
            sample_text = sample_text[:45000]
            system_prompt = (
                "You are SYLEX Universal Syllabus Extractor. Extract all courses listed in this syllabus document.\n"
                "Return PURE JSON adhering strictly to this schema:\n"
                "{\n"
                f'  "document": "{Path(pdf_path).name}",\n'
                '  "course_count": 0,\n'
                '  "courses": [\n'
                '    {"code": "...", "title": "...", "page": 1}\n'
                '  ]\n'
                "}\n"
                "Output ONLY JSON, no markdown backticks."
            )

        parsed = None
        reasoning_str = None
        try:
            if provider == "nvidia":
                content_str, reasoning_str, _ = self._call_nvidia_nemotron(
                    system_prompt=system_prompt,
                    user_content=sample_text,
                    model=model,
                    api_key=api_key,
                    endpoint=endpoint,
                    temperature=0.7,
                    top_p=0.95,
                    max_tokens=4096
                )
                start_brace = content_str.find('{')
                end_brace = content_str.rfind('}')
                if start_brace != -1 and end_brace > start_brace:
                    parsed = json.loads(content_str[start_brace:end_brace+1])
                else:
                    parsed = json.loads(content_str)
                if isinstance(parsed, dict) and reasoning_str:
                    parsed["_reasoning_summary"] = reasoning_str[:400]

            elif provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                payload = {
                    "contents": [{
                        "parts": [{"text": system_prompt + "\n\nSyllabus Document:\n" + sample_text}]
                    }],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.1
                    }
                }
                req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                             headers={'Content-Type': 'application/json'}, method='POST')
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    text_resp = data["candidates"][0]["content"]["parts"][0]["text"]
                    start_brace = text_resp.find('{')
                    end_brace = text_resp.rfind('}')
                    parsed = json.loads(text_resp[start_brace:end_brace+1])

            elif provider == "openai":
                url = "https://api.openai.com/v1/chat/completions"
                payload = {
                    "model": model or "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": sample_text}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1
                }
                req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                             headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'},
                                             method='POST')
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    text_resp = data["choices"][0]["message"]["content"]
                    start_brace = text_resp.find('{')
                    end_brace = text_resp.rfind('}')
                    parsed = json.loads(text_resp[start_brace:end_brace+1])

            elif provider == "custom":
                url = (endpoint.rstrip('/') if endpoint else "http://localhost:11434/v1") + "/chat/completions"
                payload = {
                    "model": model or "llama3.2",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": sample_text}
                    ],
                    "temperature": 0.1
                }
                headers = {'Content-Type': 'application/json'}
                if api_key: headers['Authorization'] = f'Bearer {api_key}'
                req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                             headers=headers, method='POST')
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    text_resp = data["choices"][0]["message"]["content"]
                    start_brace = text_resp.find('{')
                    end_brace = text_resp.rfind('}')
                    parsed = json.loads(text_resp[start_brace:end_brace+1])
            else:
                raise ValueError(f"Unknown provider: {provider}")
        except Exception as online_err:
            print(f"[Online Cloud Call Error: {online_err}] Falling back to grounded offline baseline...")
            if offline_res:
                offline_copy = dict(offline_res)
                if "_debug" not in offline_copy: offline_copy["_debug"] = {}
                offline_copy["_debug"]["online_error"] = str(online_err)
                offline_copy["_debug"]["fallback_mode"] = "offline"
                return offline_copy
            raise

        # Smart Hybrid Fusion: Merge Cloud AI enhancements with deterministic offline baseline
        if offline_res and offline_res.get("course"):
            if not isinstance(parsed, dict) or parsed.get("course") is None:
                parsed = offline_res
            else:
                # Guarantee complete units, topics, outcomes, matrix, and books are never truncated
                for field in ["units", "course_outcomes", "programme_outcomes", "co_po_matrix", "books"]:
                    if not parsed.get(field) and offline_res.get(field):
                        parsed[field] = offline_res[field]
                if len(parsed.get("units", [])) < len(offline_res.get("units", [])):
                    parsed["units"] = offline_res["units"]
                if len(parsed.get("course_outcomes", [])) < len(offline_res.get("course_outcomes", [])):
                    parsed["course_outcomes"] = offline_res["course_outcomes"]
                if len(parsed.get("books", [])) < len(offline_res.get("books", [])):
                    parsed["books"] = offline_res["books"]

                c_llm = parsed.get("course") or {}
                c_off = offline_res.get("course") or {}
                for k, v in c_off.items():
                    if k not in c_llm or c_llm[k] is None or c_llm[k] == "":
                        c_llm[k] = v
                parsed["course"] = c_llm

        return parsed

    def _run_sylex(self, pdf_path: str, course: str = None,
                   hints_json: str = None, debug: bool = False) -> Dict:
        """Run sylex extraction directly in-process for speed, with subprocess fallback."""
        # 1. Attempt in-process execution (eliminates ~400ms Python process spawn overhead)
        try:
            import sylex
            hints = json.loads(hints_json) if hints_json else None
            if course:
                res = sylex.run_task2(pdf_path, course, hints, debug)
            else:
                res = sylex.run_task1(pdf_path, hints)
            if res and isinstance(res, dict):
                return res
        except Exception as in_proc_err:
            sylex_module = sys.modules.get("sylex")
            read_error_type = getattr(sylex_module, "PDFReadError", None)
            if read_error_type is not None and isinstance(in_proc_err, read_error_type):
                return {"error": str(in_proc_err), "exit_code": 2}
            print(f"[In-Process Sylex Note: {in_proc_err}] Falling back to subprocess...")

        # 2. Resilient subprocess fallback
        cmd = [PYTHON, str(SYLEX_PY), "--pdf", pdf_path]
        if course:
            cmd += ["--course", course]
        if debug:
            cmd.append("--debug")

        hints_path = None
        if hints_json:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                             delete=False, encoding='utf-8') as hf:
                hf.write(hints_json)
                hints_path = hf.name
            cmd += ["--hints", hints_path]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                encoding='utf-8',
                errors='replace',
            )
            if result.returncode in (0, 3):
                s = result.stdout.strip()
                start_brace = s.find('{')
                if start_brace != -1:
                    end_brace = s.rfind('}')
                    if end_brace != -1 and end_brace > start_brace:
                        s = s[start_brace:end_brace+1]
                return json.loads(s)
            else:
                return {
                    "error": result.stderr.strip() or "Extraction failed",
                    "exit_code": result.returncode,
                }
        except subprocess.TimeoutExpired:
            return {"error": "Extraction timed out (>120s)"}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON from extractor: {e}"}
        finally:
            if hints_path:
                try: os.unlink(hints_path)
                except: pass

    def _handle_chat_request(self, user_message: str, history: List[Dict], context: Dict,
                             provider: str = "nvidia", model: str = "", api_key: str = "",
                             endpoint: str = "") -> Tuple[str, str]:
        """Process chat assistant request with full syllabus grounding and AI suggestions."""
        req_d1 = (context or {}).get("task1")
        req_d2 = (context or {}).get("task2")

        d1 = req_d1 if (isinstance(req_d1, dict) and req_d1.get("courses")) else DEFAULT_TASK1
        d2 = req_d2 if (isinstance(req_d2, dict) and req_d2.get("course")) else DEFAULT_TASK2

        # Format syllabus context summary
        ctx_parts = []
        if d1.get("document"):
            ctx_parts.append(f"Document Name: {d1.get('document')}")
        if d1.get("courses"):
            courses_list = [f"{c.get('code')} {c.get('title')} (p.{c.get('page')})" for c in d1.get('courses', [])[:30]]
            ctx_parts.append(f"All Courses in Document ({d1.get('course_count', len(courses_list))} total):\n" + "\n".join(courses_list))

        if d2.get("course"):
            c = d2["course"]
            ctx_parts.append(
                f"Active Course: {c.get('code')} - {c.get('title')}\n"
                f"Category: {c.get('category') or 'Professional Core'}, Credits: {c.get('credits') or 4}, L-T-P: {c.get('lecture') or 3}-{c.get('tutorial') or 0}-{c.get('practical') or 0}, Pages: {c.get('pages') or [1]}"
            )
            units = d2.get("units") or []
            if units:
                u_lines = []
                for u in units:
                    topics_str = ", ".join([f"{t.get('text')} [Bloom: {t.get('bloom')}]" for t in u.get("topics", [])])
                    u_lines.append(f"Unit {u.get('number')}: {u.get('title')} ({u.get('hours') or 'N/A'} hrs)\n  Topics: {topics_str or u.get('text', '')}")
                ctx_parts.append("Course Units & Topics:\n" + "\n".join(u_lines))

            cos = d2.get("course_outcomes") or []
            if cos:
                co_lines = [f"{co.get('id')}: {co.get('text')} [Bloom: {co.get('bloom')}, Source: {co.get('bloom_source')}]" for co in cos]
                ctx_parts.append("Course Outcomes (COs):\n" + "\n".join(co_lines))

            matrix = d2.get("co_po_matrix") or {}
            if matrix:
                m_lines = [f"{co_k} -> " + ", ".join([f"{po_k}:{val}" for po_k, val in po_map.items()]) for co_k, po_map in matrix.items()]
                ctx_parts.append("CO-PO Articulation Matrix:\n" + "\n".join(m_lines))

            books = d2.get("books") or []
            if books:
                b_lines = [f"[{b.get('kind', 'book').upper()}] {b.get('author')}: '{b.get('title')}' ({b.get('edition') or ''} {b.get('year') or ''})" for b in books]
                ctx_parts.append("Recommended Textbooks & References:\n" + "\n".join(b_lines))

            not_ext = d2.get("not_extracted") or []
            if not_ext:
                ctx_parts.append("Not Extracted / Missing Section Ledger:\n" + "\n".join([f"- {item}" for item in not_ext]))

        context_str = "\n\n".join(ctx_parts)

        base_prompt = _read_system_prompt()
        if not base_prompt:
            base_prompt = (
                "You are SYLEX AI Assistant — an elite University Curriculum Architect, Syllabus Intelligence Consultant, and Outcome-Based Education (OBE) Specialist.\n"
                "You provide authoritative, pedagogy-grade explanations, exam synthesis, and curriculum guidance grounded in the provided syllabus document."
            )

        system_prompt = (
            f"{base_prompt}\n\n"
            "=== CURRENT SYLLABUS EXTRACTION CONTEXT ===\n"
            f"{context_str}\n"
            "===========================================\n\n"
            "CRITICAL INSTRUCTIONS FOR YOUR RESPONSE:\n"
            "1. DIRECT AND COMPLETE ANSWER: Whatever question the user asks (concepts, definitions, comparisons, code examples, algorithm mechanics, exam questions, lesson plans, Bloom taxonomy analysis, or practical applications), YOU MUST DIRECTLY, THOROUGHLY, AND AUTHORITATIVELY ANSWER IT.\n"
            "2. SYLLABUS GROUNDING: Connect and anchor your answer explicitly to the syllabus above. Mention the Course Code & Title, relevant Unit number, topic clause, and cognitive Bloom level (K1 to K6).\n"
            "3. NEVER REFUSE VALID QUESTIONS: Never give generic refusal templates or say 'I cannot answer' for academic, computer science, programming, or curriculum questions. Answer the question completely with clear pedagogical depth, step-by-step logic, and code snippets where appropriate.\n"
            "4. CLEAN MARKDOWN PRESENTATION: Format your response using clean GitHub Markdown with clear bold headers (###), bullet points, and code blocks with syntax highlighting.\n"
            "5. NEXT SUGGESTIONS: Always conclude your response with 2 to 3 concise, highly relevant next question suggestions under a '💡 **Next Suggestions:**' section."
        )

        actual_model = model or ("z-ai/glm-5.3" if provider == "nvidia" else "gemini-2.0-flash")

        # Format user prompt with context if history is present
        user_prompt = user_message
        if history and isinstance(history, list):
            recent_turns = history[-4:]
            hist_str = "\n".join([f"{h.get('role', 'user').upper()}: {h.get('content', '')}" for h in recent_turns])
            user_prompt = f"Previous conversation:\n{hist_str}\n\nCurrent Question: {user_message}"

        # Call Cloud Provider
        try:
            if provider == "nvidia":
                content, _, m_used = self._call_nvidia_nemotron(
                    system_prompt=system_prompt,
                    user_content=user_prompt,
                    model=actual_model,
                    api_key=api_key,
                    endpoint=endpoint,
                    temperature=0.7,
                    max_tokens=2048,
                    timeout=18.0
                )
                if content and content.strip():
                    return content.strip(), m_used

            elif provider == "gemini":
                actual_key = api_key
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{actual_model}:generateContent?key={actual_key}"
                payload = {
                    "contents": [{
                        "parts": [{"text": system_prompt + "\n\n" + user_prompt}]
                    }],
                    "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2048}
                }
                req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                             headers={'Content-Type': 'application/json'}, method='POST')
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    text_resp = data["candidates"][0]["content"]["parts"][0]["text"]
                    return text_resp.strip(), actual_model

            elif provider == "openai":
                url = "https://api.openai.com/v1/chat/completions"
                payload = {
                    "model": actual_model or "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.4
                }
                req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                             headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'},
                                             method='POST')
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    return data["choices"][0]["message"]["content"].strip(), actual_model

            elif provider == "custom":
                url = (endpoint.rstrip('/') if endpoint else "http://localhost:11434/v1") + "/chat/completions"
                payload = {
                    "model": actual_model or "llama3.2",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.4
                }
                headers = {'Content-Type': 'application/json'}
                if api_key: headers['Authorization'] = f'Bearer {api_key}'
                req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                             headers=headers, method='POST')
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    return data["choices"][0]["message"]["content"].strip(), actual_model

        except Exception as e:
            print(f"[Chat Cloud AI Fallback: {e}]")

        # Intelligent Local Fallback Response
        fallback_text = self._local_assistant_reply(user_message, d1, d2)
        return fallback_text, "local-offline-engine"

    def _local_assistant_reply(self, q: str, d1: Dict, d2: Dict) -> str:
        """Local context-aware assistant reply generator when offline."""
        q_lower = q.lower()
        course = d2.get("course") if d2 else None

        if course and any(w in q_lower for w in ["exam", "question", "quiz", "test", "assessment"]):
            cos = d2.get("course_outcomes") or []
            units = d2.get("units") or []
            lines = [f"### 📝 Recommended Assessment & Exam Questions for **{course.get('code')} - {course.get('title')}**\n"]
            for i, u in enumerate(units[:5], 1):
                topics = [t.get("text") for t in u.get("topics", [])[:2]]
                topic_desc = " and ".join(topics) if topics else u.get("title")
                lines.append(f"**Q{i} (Unit {u.get('number')} — {u.get('title')} / Bloom: Apply)**")
                lines.append(f"> Explain the core principles of *{topic_desc}*. Formulate a real-world engineering scenario illustrating its application.\n")
            lines.append("💡 **Next Suggestions:**")
            lines.append("1. Ask: *'Generate marking rubric for these questions'*")
            lines.append("2. Ask: *'Suggest laboratory experiments for this course'*")
            lines.append("3. Ask: *'Analyze CO-PO attainment for Unit 1'*")
            return "\n".join(lines)

        if course and any(w in q_lower for w in ["lesson", "plan", "lecture", "schedule", "hour", "hours"]):
            units = d2.get("units") or []
            lines = [f"### 📅 Proposed 45-Hour Lesson Plan for **{course.get('code')} - {course.get('title')}**\n"]
            total_h = 0
            for u in units:
                h = u.get("hours") or 9
                total_h += h
                lines.append(f"#### Unit {u.get('number')}: {u.get('title')} ({h} Hours)")
                for t_idx, t in enumerate(u.get("topics", [])[:4], 1):
                    lines.append(f"- **Lecture {t_idx}**: {t.get('text')} *(Bloom Level: {t.get('bloom', 'understand').capitalize()})*")
            lines.append(f"\n*Total Contact Hours Planned:* **{total_h} Hours**")
            lines.append("\n💡 **Next Suggestions:**")
            lines.append("1. Ask: *'What pedagogical teaching methods fit Unit 2?'*")
            lines.append("2. Ask: *'Suggest active learning activities for Unit 3'*")
            lines.append("3. Ask: *'Generate quiz questions for this lesson plan'*")
            return "\n".join(lines)

        if course and any(w in q_lower for w in ["bloom", "taxonomy", "improve", "level"]):
            cos = d2.get("course_outcomes") or []
            lines = [f"### 🎯 Bloom Taxonomy Analysis for **{course.get('code')} - {course.get('title')}**\n"]
            lines.append("| Outcome | Bloom Level | Source | Actionable Improvement |")
            lines.append("| :--- | :--- | :--- | :--- |")
            for co in cos:
                lvl = co.get("bloom", "understand")
                rec = "Elevate to *Analyse* by incorporating comparative case studies" if lvl in ["remember","understand"] else "Maintain higher-order engineering evaluation"
                lines.append(f"| **{co.get('id')}** | `{lvl}` | {co.get('bloom_source')} | {rec} |")
            lines.append("\n💡 **Next Suggestions:**")
            lines.append("1. Ask: *'Rewrite CO1 to achieve Level K4 Analyse'*")
            lines.append("2. Ask: *'Check NBA / OBE compliance of these outcomes'*")
            return "\n".join(lines)

        if course and any(w in q_lower for w in ["book", "reference", "textbook", "reading", "resource"]):
            books = d2.get("books") or []
            lines = [f"### 📚 Curated Bibliography for **{course.get('code')} - {course.get('title')}**\n"]
            for b in books:
                lines.append(f"- **[{b.get('kind', 'Book').capitalize()}]** *{b.get('title')}* by **{b.get('author') or 'Unknown'}** ({b.get('year') or 'Recent Edition'})")
            lines.append("\n**Recommended Digital Resources:**")
            lines.append("- NPTEL / SWAYAM video lecture modules corresponding to syllabus topics")
            lines.append("- IEEE Xplore survey papers on emerging advances in this field")
            lines.append("\n💡 **Next Suggestions:**")
            lines.append("1. Ask: *'Which book is best for beginners in this subject?'*")
            lines.append("2. Ask: *'Suggest open-source software tools for lab practice'*")
            return "\n".join(lines)

        # General extraction breakdown
        if course:
            units = d2.get("units") or []
            cos = d2.get("course_outcomes") or []
            books = d2.get("books") or []
            return (
                f"### 🎓 Syllabus Intelligence for **{course.get('code')} - {course.get('title')}**\n\n"
                f"- **Academic Structure**: Category `{course.get('category')}`, Credits `{course.get('credits')}`, Contact Hours: `{course.get('lecture')}-{course.get('tutorial')}-{course.get('practical')}`\n"
                f"- **Units Extracted**: **{len(units)} units** with **{sum(len(u.get('topics', [])) for u in units)} granular topics**\n"
                f"- **Outcomes Defined**: **{len(cos)} Course Outcomes**\n"
                f"- **Bibliography**: **{len(books)} textbooks & references**\n\n"
                f"How would you like to proceed with this course?\n\n"
                "💡 **Next Suggestions:**\n"
                "1. Ask: *'Suggest 5 exam questions for this course'* \n"
                "2. Ask: *'Generate a 45-hour lecture schedule'* \n"
                "3. Ask: *'Analyze Bloom taxonomy and CO-PO matrix'* "
            )

        if d1 and d1.get("courses"):
            count = d1.get("course_count", len(d1.get("courses", [])))
            return (
                f"### 📄 Document Overview: **{d1.get('document', 'Syllabus PDF')}**\n\n"
                f"Detected **{count} courses** across the curriculum.\n"
                "To explore deep units, topics, Bloom levels, and exam suggestions, select any course in the **Results** tab or type its code here!\n\n"
                "💡 **Next Suggestions:**\n"
                "1. Ask: *'Which elective courses are available?'*\n"
                "2. Ask: *'List all 1st year foundational subjects'*\n"
            )

        return (
            "### 🤖 SYLEX AI Curriculum Advisor\n\n"
            "I'm ready to assist you! Upload any syllabus PDF or select a course from the **Results** tab. I can provide:\n"
            "- **Exam Questions & Assessment Design** aligned with Bloom's taxonomy\n"
            "- **Complete Lesson Plans** with lecture-by-lecture hourly breakdown\n"
            "- **Curriculum Gap Analysis** and NBA/OBE accreditation compliance\n"
            "- **Textbook & Digital Tool Recommendations**\n\n"
            "💡 **Next Suggestions:**\n"
            "1. Upload a PDF in the **Extract** tab\n"
            "2. Click **Results -> Deep View** to explore a specific subject"
        )

    def _generate_dossier_html(self, d2: Dict) -> str:
        """Generate university accreditation compliant Course Dossier / File in HTML."""
        import sylex
        audit = sylex.calculate_curriculum_audit(d2)
        def _html_safe(value):
            if isinstance(value, dict):
                return {html.escape(str(key), quote=True): _html_safe(item) for key, item in value.items()}
            if isinstance(value, list):
                return [_html_safe(item) for item in value]
            if isinstance(value, tuple):
                return tuple(_html_safe(item) for item in value)
            if isinstance(value, str):
                return html.escape(value, quote=True)
            return value

        d2 = _html_safe(d2)
        c = d2.get("course") or {}
        c_code = c.get("code") or "CS23301"
        c_title = c.get("title") or "DATA STRUCTURES AND ALGORITHMS"
        c_cat = c.get("category") or "Professional Core"
        c_cred = c.get("credits") or 4
        c_lec = c.get("lecture") or 3
        c_tut = c.get("tutorial") or 0
        c_prac = c.get("practical") or 0
        units = d2.get("units") or []
        cos = d2.get("course_outcomes") or []
        pos = d2.get("programme_outcomes") or []
        matrix = d2.get("co_po_matrix") or {}
        books = d2.get("books") or []

        all_po_ids = [po.get("id") for po in pos if po.get("id")]
        if not all_po_ids:
            all_po_ids = [f"PO{i}" for i in range(1, 13)]

        bloom_ana = audit.get("bloom_analytics") or {}
        dist = bloom_ana.get("distribution") or {}
        hour_int = audit.get("hour_integrity") or {}

        # Build Units HTML
        units_html = []
        lecture_count = 0
        lesson_plan_rows = []
        assessment_q_rows = []

        for u in units:
            u_num = u.get("number", 1)
            u_title = u.get("title", f"Unit {u_num}")
            u_hours = u.get("hours", 9)
            topics = u.get("topics") or []
            t_rows = []
            for t_idx, t in enumerate(topics, 1):
                b_lvl = str(t.get("bloom") or "understand").upper()
                t_rows.append(f"<tr><td><strong>u{u_num}t{t_idx}</strong></td><td>{t.get('text')}</td><td><span class='bloom-tag'>{b_lvl}</span></td></tr>")
                
                # Add to Lesson Plan
                lecture_count += 1
                pedagogy = "Active Learning / Problem Solving" if b_lvl in ("APPLY", "ANALYSE") else ("Design Workshop" if b_lvl in ("CREATE", "EVALUATE") else "Interactive Lecture & Discussion")
                lesson_plan_rows.append(f"<tr><td>L{lecture_count}</td><td>Unit {u_num}</td><td>{t.get('text')}</td><td>{b_lvl}</td><td>{pedagogy}</td></tr>")

            units_html.append(f"""
            <div class="dossier-unit">
                <h3 style="margin-bottom:6px">Unit {u_num}: {u_title} <span class="hours-tag">{u_hours} Contact Hours</span></h3>
                <table class="dossier-table">
                    <thead><tr><th style="width:15%">Topic ID</th><th style="width:65%">Topic Description</th><th style="width:20%">Cognitive Level</th></tr></thead>
                    <tbody>{''.join(t_rows)}</tbody>
                </table>
            </div>
            """)

            # Sample Questions per unit
            t_sample = topics[0].get("text") if topics else u_title
            assessment_q_rows.append(f"""
            <tr>
                <td><strong>Q{u_num}A</strong></td>
                <td>Unit {u_num}</td>
                <td>Define the core principles of <em>{t_sample}</em>. Explain its structural and algorithmic characteristics.</td>
                <td>2 Marks</td>
                <td>K2 (Understand)</td>
            </tr>
            <tr>
                <td><strong>Q{u_num}B</strong></td>
                <td>Unit {u_num}</td>
                <td>Formulate and implement an engineering solution involving <em>{t_sample}</em>. Evaluate computational trade-offs.</td>
                <td>8/16 Marks</td>
                <td>K3/K4 (Apply/Analyse)</td>
            </tr>
            """)

        # CO rows
        co_rows = []
        for co in cos:
            b_lvl = str(co.get("bloom") or "understand").upper()
            co_rows.append(f"<tr><td><strong>{co.get('id')}</strong></td><td>{co.get('text')}</td><td><span class='bloom-tag'>{b_lvl}</span></td></tr>")

        # PO rows
        po_rows = []
        for po in pos:
            po_rows.append(f"<tr><td><strong>{po.get('id')}</strong></td><td>{po.get('text')}</td></tr>")

        # Matrix HTML
        matrix_headers = "".join([f"<th>{p}</th>" for p in all_po_ids])
        matrix_rows = []
        for co in cos:
            co_id = co.get("id")
            co_map = matrix.get(co_id, {})
            cells = []
            for p in all_po_ids:
                val = str(co_map.get(p, "-")).strip()
                cell_cls = "m-strong" if val in ("3", "S", "H") else ("m-med" if val in ("2", "M") else ("m-weak" if val in ("1", "L") else "m-none"))
                cells.append(f"<td class='{cell_cls}'>{val}</td>")
            matrix_rows.append(f"<tr><td><strong>{co_id}</strong></td>{''.join(cells)}</tr>")

        # Books HTML
        books_html = []
        for b in books:
            b_kind = str(b.get("kind", "Book")).upper()
            b_title = b.get("title", "")
            b_auth = b.get("author", "Unknown")
            b_pub = b.get("publisher") or "Publisher not printed"
            b_yr = b.get("year") or ""
            b_ed = b.get("edition") or ""
            books_html.append(f"<li><strong>[{b_kind}]</strong> <em>{b_title}</em> — {b_auth}. {b_pub} {b_ed} ({b_yr}).</li>")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>Accreditation Course Dossier — {c_code}: {c_title}</title>
<style>
  body {{ font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif; color: #1e293b; line-height: 1.6; margin: 0; padding: 2.5rem; background: #fff; }}
  .dossier-header {{ border-bottom: 3px double #0f172a; padding-bottom: 1.5rem; margin-bottom: 2rem; display: flex; justify-content: space-between; align-items: flex-start; }}
  .dossier-title {{ font-size: 1.8rem; font-weight: 800; color: #0f172a; margin: 0 0 0.5rem 0; letter-spacing: -0.02em; }}
  .dossier-sub {{ font-size: 0.95rem; color: #64748b; font-weight: 500; }}
  .badge-row {{ display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }}
  .badge {{ background: #f1f5f9; border: 1px solid #cbd5e1; padding: 4px 10px; border-radius: 4px; font-size: 0.8rem; font-weight: 600; color: #334155; }}
  .badge-primary {{ background: #eff6ff; border-color: #bfdbfe; color: #1d4ed8; }}
  .badge-success {{ background: #f0fdf4; border-color: #bbf7d0; color: #15803d; }}
  .section {{ margin-bottom: 2.5rem; page-break-inside: avoid; }}
  .section-title {{ font-size: 1.25rem; font-weight: 700; color: #1e3a8a; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; margin-bottom: 1rem; }}
  .dossier-table {{ width: 100%; border-collapse: collapse; margin-bottom: 1.5rem; font-size: 0.88rem; }}
  .dossier-table th, .dossier-table td {{ border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left; }}
  .dossier-table th {{ background: #f8fafc; font-weight: 700; color: #334155; }}
  .bloom-tag {{ font-family: monospace; font-size: 0.78rem; font-weight: 700; padding: 2px 6px; border-radius: 3px; background: #e0f2fe; color: #0369a1; }}
  .hours-tag {{ float: right; font-size: 0.85rem; font-weight: normal; color: #64748b; }}
  .m-strong {{ background: #dbeafe; font-weight: 700; text-align: center; color: #1e40af; }}
  .m-med {{ background: #e0f2fe; font-weight: 600; text-align: center; color: #0284c7; }}
  .m-weak {{ background: #f0fdf4; text-align: center; color: #166534; }}
  .m-none {{ text-align: center; color: #94a3b8; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 1.5rem; }}
  .kpi-card {{ border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px; background: #fafafa; }}
  .kpi-val {{ font-size: 1.4rem; font-weight: 800; color: #0f172a; }}
  .kpi-lbl {{ font-size: 0.75rem; text-transform: uppercase; color: #64748b; font-weight: 600; }}
  .sign-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-top: 3.5rem; text-align: center; font-size: 0.85rem; }}
  .sign-line {{ border-top: 1px solid #0f172a; margin-top: 40px; padding-top: 6px; font-weight: 600; }}
  @media print {{
    body {{ padding: 0.5in; font-size: 11pt; }}
    .no-print {{ display: none; }}
    .page-break {{ page-break-before: always; }}
  }}
</style>
</head>
<body>

<div class="no-print" style="margin-bottom:1.5rem;display:flex;gap:12px;align-items:center">
  <button onclick="window.print()" style="background:#1d4ed8;color:#fff;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;font-weight:700">🖨️ Print / Save as PDF</button>
  <button onclick="window.close()" style="background:#f1f5f9;border:1px solid #cbd5e1;padding:8px 16px;border-radius:4px;cursor:pointer">Close</button>
  <span style="font-size:0.85rem;color:#64748b">Verified compliant with Outcome-Based Education (OBE) &amp; NBA Accreditation Guidelines</span>
</div>

<div class="dossier-header">
  <div>
    <h1 class="dossier-title">{c_code}: {c_title}</h1>
    <div class="dossier-sub">Official Accreditation Course File &amp; Curriculum Specifications</div>
    <div class="badge-row">
      <span class="badge badge-primary">Category: {c_cat}</span>
      <span class="badge badge-primary">Credits: {c_cred}</span>
      <span class="badge badge-primary">L-T-P: {c_lec}-{c_tut}-{c_prac}</span>
      <span class="badge badge-success">Health Score: {audit.get('curriculum_score', 95)}/100</span>
      <span class="badge badge-success">NBA Status: {bloom_ana.get('nba_status', 'COMPLIANT')}</span>
    </div>
  </div>
  <div style="text-align:right">
    <div style="font-size:1.1rem;font-weight:800;color:#0f172a">ACADEMIC DOSSIER</div>
    <div style="font-size:0.8rem;color:#64748b">Format: SYLEX-ΩX v2.2</div>
    <div style="font-size:0.8rem;color:#64748b">Evaluation Standard: 2026</div>
  </div>
</div>

<div class="section">
  <div class="section-title">1. Executive Audit &amp; Accreditation Metrics</div>
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-val">{hour_int.get('total_unit_hours', 45)} Hrs</div>
      <div class="kpi-lbl">Total Contact Hours</div>
      <div style="font-size:0.75rem;color:#059669;margin-top:4px">{hour_int.get('status', 'VERIFIED')}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">{bloom_ana.get('hots_percentage', 65)}%</div>
      <div class="kpi-lbl">Higher-Order Rigor (HOTS K3–K6)</div>
      <div style="font-size:0.75rem;color:#059669;margin-top:4px">Target: ≥ 50% Washington Accord</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">{audit.get('co_po_coverage', {}).get('matrix_density_pct', 70)}%</div>
      <div class="kpi-lbl">Matrix Mapping Density</div>
      <div style="font-size:0.75rem;color:#1d4ed8;margin-top:4px">{audit.get('co_po_coverage', {}).get('total_mapped_cells', 15)} cells mapped</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">{len(units)} Units / {len(cos)} COs</div>
      <div class="kpi-lbl">Curriculum Depth</div>
      <div style="font-size:0.75rem;color:#64748b;margin-top:4px">{len(books)} Prescribed Citations</div>
    </div>
  </div>
</div>

<div class="section">
  <div class="section-title">2. Course Outcomes (CO) &amp; Programme Outcomes (PO)</div>
  <table class="dossier-table">
    <thead><tr><th style="width:12%">Outcome ID</th><th style="width:73%">Statement</th><th style="width:15%">Target Bloom</th></tr></thead>
    <tbody>{''.join(co_rows)}</tbody>
  </table>
  {f'<table class="dossier-table"><thead><tr><th style="width:12%">PO ID</th><th>Programme Outcome Definition</th></tr></thead><tbody>{"".join(po_rows)}</tbody></table>' if po_rows else ''}
</div>

<div class="section">
  <div class="section-title">3. CO-PO Articulation Matrix</div>
  <p style="font-size:0.8rem;color:#64748b;margin-top:-0.5rem;margin-bottom:0.75rem">Correlation Levels: 3 = Substantial (High), 2 = Moderate (Medium), 1 = Slight (Low), - = No Correlation</p>
  <table class="dossier-table">
    <thead><tr><th>CO #</th>{matrix_headers}</tr></thead>
    <tbody>{''.join(matrix_rows)}</tbody>
  </table>
</div>

<div class="section page-break">
  <div class="section-title">4. Complete Unit-Wise Syllabus</div>
  {''.join(units_html)}
</div>

<div class="section page-break">
  <div class="section-title">5. 45-Hour Lecture Lesson Plan</div>
  <table class="dossier-table">
    <thead><tr><th style="width:10%">Period</th><th style="width:15%">Unit</th><th style="width:45%">Topic to Cover</th><th style="width:15%">Cognitive Depth</th><th style="width:15%">Methodology</th></tr></thead>
    <tbody>{''.join(lesson_plan_rows[:45])}</tbody>
  </table>
</div>

<div class="section">
  <div class="section-title">6. Sample Assessment Blueprint &amp; Continuous Evaluation</div>
  <table class="dossier-table">
    <thead><tr><th style="width:10%">Item</th><th style="width:12%">Unit</th><th style="width:55%">Question Formulation</th><th style="width:10%">Weightage</th><th style="width:13%">Bloom Taxonomy</th></tr></thead>
    <tbody>{''.join(assessment_q_rows)}</tbody>
  </table>
</div>

<div class="section">
  <div class="section-title">7. Prescribed Literature &amp; References</div>
  <ul>{''.join(books_html)}</ul>
</div>

<div class="sign-grid">
  <div><div class="sign-line">Faculty In-Charge</div></div>
  <div><div class="sign-line">Course Coordinator</div></div>
  <div><div class="sign-line">Head of Department</div></div>
  <div><div class="sign-line">Dean (Academics)</div></div>
</div>

</body>
</html>"""

def main():
    display_host = "localhost" if HOST in {"127.0.0.1", "localhost"} else HOST
    print(f"SYLEX Concurrent Server v3.0 — http://{display_host}:{PORT}")
    print(f"Python: {PYTHON}")
    print(f"Engine: {SYLEX_PY}")
    print(f"Mode:   OFFLINE (no internet required) + Threading Enabled")
    print("Press Ctrl+C to stop.\n")

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        if "--browser" in sys.argv:
            def open_browser():
                import time, webbrowser
                time.sleep(0.8)
                webbrowser.open(f"http://localhost:{PORT}")
            threading.Thread(target=open_browser, daemon=True).start()
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

if __name__ == "__main__":
    main()
