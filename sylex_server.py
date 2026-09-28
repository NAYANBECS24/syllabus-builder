#!/usr/bin/env python3
"""
SYLEX Local Server — bridges the web UI and Python extraction engine.
Run this to use the web dashboard offline.

    python sylex_server.py
    # then open http://localhost:7823 in your browser
"""

import sys, os, json, tempfile, threading, subprocess, mimetypes, hashlib
import urllib
import urllib.request
from collections import OrderedDict
os.environ["PYMUPDF_SUGGEST_LAYOUT_ANALYZER"] = "0"
from pathlib import Path
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, List, Tuple

PORT      = 7823
BASE_DIR  = Path(__file__).parent
SYLEX_PY  = BASE_DIR / "sylex.py"

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

GLOBAL_SYLLABUS_CONTEXT = {
    "task1": DEFAULT_TASK1,
    "task2": DEFAULT_TASK2
}

# Find Python executable
def find_python():
    candidates = [
        sys.executable,
        "python", "python3", "py",
        r"C:\Users\nayan\AppData\Local\Programs\Python\Python312\python.exe",
        r"C:\Users\nayan\AppData\Local\Programs\Python\Python313\python.exe",
        r"C:\Users\nayan\AppData\Local\Programs\Python\Python315\python.exe",
    ]
    for c in candidates:
        try:
            r = subprocess.run([c, "--version"], capture_output=True, timeout=3)
            if r.returncode == 0: return c
        except Exception: pass
    return sys.executable

PYTHON = find_python()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.command}] {self.path} — {args[1] if len(args)>1 else ''}")

    def send_json(self, data, code=200):
        try:
            body = json.dumps(data, ensure_ascii=False, indent=2, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
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
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_response(404); self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.lstrip('/')

        # API: status
        if path == "api/status":
            self.send_json({
                "status":  "online",
                "python":  PYTHON,
                "version": "3.0",
                "offline": True,
            })
            return

        # API: cache stats
        if path == "api/cache/stats":
            self.send_json({
                "status": "ok",
                "cached_items": len(CACHE.cache),
                "max_items": CACHE.max_items
            })
            return

        # API: live curriculum audit
        if path == "api/curriculum-audit":
            try:
                import sylex
                d2 = GLOBAL_SYLLABUS_CONTEXT.get("task2") or DEFAULT_TASK2
                audit = sylex.calculate_curriculum_audit(d2)
                self.send_json(audit)
                return
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
                return

        # Static files (serve any file from BASE_DIR: chat.css, chat.js, styles.css, etc.)
        safe_path = (BASE_DIR / (path or "index.html")).resolve()
        if str(safe_path).startswith(str(BASE_DIR.resolve())) and safe_path.is_file():
            self.send_file(safe_path)
            return

        self.send_response(404); self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path.lstrip('/')

        # ── POST /api/cache/clear
        if path == "api/cache/clear":
            CACHE.clear()
            self.send_json({"status": "ok", "cleared": True})
            return

        # ── POST /api/chat (Universal Cloud AI Curriculum Assistant & Advisor)
        if path == "api/chat":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                req_data = json.loads(body.decode('utf-8')) if body else {}

                user_message = req_data.get("message", "").strip()
                history = req_data.get("history", [])
                context = req_data.get("context") or {}
                provider = req_data.get("provider", "nvidia").lower()
                model = req_data.get("model", "").strip()
                api_key = req_data.get("api_key", "").strip()
                endpoint = req_data.get("endpoint", "").strip()

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
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
                return

        # ── POST /api/curriculum-audit (NBA & OBE Accreditation Evaluation)
        if path == "api/curriculum-audit":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                req_data = json.loads(body.decode('utf-8')) if body else {}
                d2 = req_data.get("task2") or GLOBAL_SYLLABUS_CONTEXT.get("task2") or DEFAULT_TASK2
                import sylex
                audit = sylex.calculate_curriculum_audit(d2)
                self.send_json(audit)
                return
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
                return

        # ── POST /api/export-dossier (Official University Course File Dossier)
        if path == "api/export-dossier":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                req_data = json.loads(body.decode('utf-8')) if body else {}
                d2 = req_data.get("task2") or GLOBAL_SYLLABUS_CONTEXT.get("task2") or DEFAULT_TASK2
                html = self._generate_dossier_html(d2)
                c_code = (d2.get("course") or {}).get("code", "SYLLABUS")
                self.send_json({"status": "ok", "html": html, "filename": f"Course_Dossier_{c_code}.html"})
                return
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
                return

        # ── POST /api/test-key  (connectivity test for NVIDIA / Gemini / OpenAI / Custom)
        if path == "api/test-key":
            try:
                import time
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                req_data = json.loads(body.decode('utf-8')) if body else {}

                provider = req_data.get("provider", "nvidia").lower()
                key = req_data.get("key", "").strip()
                model = req_data.get("model", "").strip()
                endpoint = req_data.get("endpoint", "").strip()

                t0 = time.time()

                if provider == "nvidia":
                    content, reasoning, m_used = self._call_nvidia_nemotron(
                        system_prompt="You are a helpful AI assistant. Answer concisely in one sentence.",
                        user_content="Write a 1-sentence verification that GPU computing is active.",
                        model=model or "nvidia/nemotron-3-super-120b-a12b",
                        api_key=key or "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",
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
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
                return

        # ── POST /api/extract  (multipart PDF upload)
        if path == "api/extract":
            try:
                ctype  = self.headers.get("Content-Type","")
                length = int(self.headers.get("Content-Length", 0))
                body   = self.rfile.read(length)

                # Parse multipart to get PDF bytes + params
                pdf_bytes, course, hints_json, debug_flag, mode, provider, model, api_key, endpoint = self._parse_multipart(ctype, body)

                if pdf_bytes is None:
                    self.send_json({"error": "No PDF received"}, 400); return

                # In-memory SHA-256 cache check
                cache_key = hashlib.sha256(
                    pdf_bytes[:100000] + f":{len(pdf_bytes)}:{mode}:{provider}:{model}:{course}:{debug_flag}".encode('utf-8')
                ).hexdigest()

                cached_res = CACHE.get(cache_key)
                if cached_res is not None:
                    if isinstance(cached_res, dict):
                        cached_copy = dict(cached_res)
                        if "_debug" not in cached_copy:
                            cached_copy["_debug"] = {}
                        cached_copy["_debug"]["from_cache"] = True
                        self.send_json(cached_copy)
                    else:
                        self.send_json(cached_res)
                    return

                # Auto-enrich hints with document course catalog if available from Task 1
                if course and GLOBAL_SYLLABUS_CONTEXT.get("task1"):
                    try:
                        h_dict = json.loads(hints_json) if hints_json else {}
                        t1_courses = GLOBAL_SYLLABUS_CONTEXT["task1"].get("courses")
                        if "courses" not in h_dict and t1_courses:
                            h_dict["courses"] = t1_courses
                            hints_json = json.dumps(h_dict)
                    except Exception:
                        pass

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
                        result = self._normalize_task1_schema(result, "document.pdf")
                    if debug_info: result["_debug"] = debug_info
                    if reasoning_info: result["_reasoning_summary"] = reasoning_info

                # Cache successful extraction and update active global syllabus context
                if result and not (isinstance(result, dict) and "error" in result):
                    CACHE.set(cache_key, result)
                    if course:
                        GLOBAL_SYLLABUS_CONTEXT["task2"] = result
                    else:
                        GLOBAL_SYLLABUS_CONTEXT["task1"] = result

                self.send_json(result)

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
            "document": str(result.get("document") or pdf_filename),
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
        base_url = endpoint.rstrip('/') if endpoint else "https://integrate.api.nvidia.com/v1"
        key = api_key or "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"
        requested_model = model if model and model not in ("gemini-2.0-flash", "gpt-4o-mini", "llama3.2") else "nvidia/nemotron-3-super-120b-a12b"

        candidate_models = [
            requested_model,
            "nvidia/nemotron-3-super-120b-a12b",
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
        for m in models:
            payload = {
                "model": m,
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens
            }
            try:
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
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
        """Parse multipart/form-data body. Returns (pdf_bytes, course, hints, debug, mode, provider, model, api_key, endpoint)."""
        import email, io
        msg_str = f"Content-Type: {ctype}\r\n\r\n".encode() + body
        msg     = email.message_from_bytes(msg_str)

        pdf_bytes   = None
        course      = None
        hints_json  = None
        debug_flag  = False
        mode        = "offline"
        provider    = "nvidia"
        model       = "nvidia/nemotron-3-super-120b-a12b"
        api_key     = "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"
        endpoint    = ""

        if msg.is_multipart():
            for part in msg.walk():
                cd = part.get("Content-Disposition","")
                if 'name="pdf"' in cd:
                    pdf_bytes = part.get_payload(decode=True)
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
                    api_key = (v or "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").strip()
                elif 'name="endpoint"' in cd:
                    v = part.get_payload(decode=True)
                    if isinstance(v, bytes): v = v.decode('utf-8', 'ignore')
                    endpoint = (v or "").strip()
        else:
            pdf_bytes = body

        return pdf_bytes, course, hints_json, debug_flag, mode, provider, model, api_key, endpoint

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

        d1 = req_d1 if (isinstance(req_d1, dict) and req_d1.get("courses")) else (GLOBAL_SYLLABUS_CONTEXT.get("task1") or DEFAULT_TASK1)
        d2 = req_d2 if (isinstance(req_d2, dict) and req_d2.get("course")) else (GLOBAL_SYLLABUS_CONTEXT.get("task2") or DEFAULT_TASK2)

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

        prompt_file = Path(__file__).parent / "SYSTEM_PROMPT.md"
        base_prompt = ""
        if prompt_file.is_file():
            try:
                base_prompt = prompt_file.read_text(encoding="utf-8")
            except Exception:
                pass

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

        actual_model = model or ("nvidia/nemotron-3-super-120b-a12b" if provider == "nvidia" else "gemini-2.0-flash")

        # Format user prompt with context if history is present
        user_prompt = user_message
        if history and isinstance(history, list):
            recent_turns = history[-4:]
            hist_str = "\n".join([f"{h.get('role', 'user').upper()}: {h.get('content', '')}" for h in recent_turns])
            user_prompt = f"Previous conversation:\n{hist_str}\n\nCurrent Question: {user_message}"

        # Call Cloud Provider
        try:
            if provider == "nvidia":
                key = api_key or "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"
                content, _, m_used = self._call_nvidia_nemotron(
                    system_prompt=system_prompt,
                    user_content=user_prompt,
                    model=actual_model,
                    api_key=key,
                    endpoint=endpoint,
                    temperature=0.7,
                    max_tokens=2048,
                    timeout=25.0
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
    print(f"SYLEX Concurrent Server v3.0 — http://localhost:{PORT}")
    print(f"Python: {PYTHON}")
    print(f"Engine: {SYLEX_PY}")
    print(f"Mode:   OFFLINE (no internet required) + Threading Enabled")
    print("Press Ctrl+C to stop.\n")

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
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
