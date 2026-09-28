 #!/usr/bin/env python3
"""
SYLEX — run.py
Single entry point for everything.

Usage:
    python run.py                          # open web UI (auto-launches browser)
    python run.py --pdf syllabus.pdf       # Task 1 (CLI)
    python run.py --pdf syllabus.pdf --course CS23301   # Task 2 (CLI)
    python run.py --pdf syllabus.pdf --debug             # with debug output
    python run.py --pdf syllabus.pdf --hints hints.json  # with hints
    python run.py --server                 # just start server without browser
    python run.py --install                # install required packages
"""

import sys
import os
import subprocess
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SYLEX    = os.path.join(BASE_DIR, "sylex.py")
SERVER   = os.path.join(BASE_DIR, "sylex_server.py")

# ── Find Python ────────────────────────────────────────────────────
def find_python():
    candidates = [
        sys.executable,
        "python", "python3",
        r"C:\Users\nayan\AppData\Local\Programs\Python\Python312\python.exe",
        r"C:\Users\nayan\AppData\Local\Programs\Python\Python313\python.exe",
        r"C:\Users\nayan\AppData\Local\Programs\Python\Python315\python.exe",
    ]
    for c in candidates:
        try:
            r = subprocess.run([c, "--version"], capture_output=True, timeout=3)
            if r.returncode == 0:
                return c
        except Exception:
            pass
    return sys.executable

PY = find_python()

# ── Dependency check ───────────────────────────────────────────────
REQUIRED = ["pdfplumber", "pymupdf"]

def check_deps():
    missing = []
    for pkg in REQUIRED:
        try:
            __import__(pkg if pkg != "pymupdf" else "pymupdf")
        except ImportError:
            # Try fitz (older name for pymupdf)
            if pkg == "pymupdf":
                try:
                    __import__("fitz")
                    continue
                except ImportError:
                    pass
            missing.append(pkg)
    return missing

def install_deps():
    print("Installing required packages...")
    subprocess.run([PY, "-m", "pip", "install", "pdfplumber", "PyMuPDF", "-q"], check=True)
    print("✅ Done — packages installed.\n")

# ── Main ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="SYLEX v3.0 — Syllabus Extraction Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                                      Open web UI
  python run.py --pdf syllabus.pdf                   Task 1
  python run.py --pdf syllabus.pdf --course CS23301  Task 2
  python run.py --install                            Install dependencies
  python run.py --server                             Start server only
"""
    )
    parser.add_argument("--pdf",     default=None, help="Path to syllabus PDF")
    parser.add_argument("--course",  default=None, help="Course code (Task 2)")
    parser.add_argument("--out",     default=None, help="Output JSON file path")
    parser.add_argument("--hints",   default=None, help="Hints JSON file path")
    parser.add_argument("--debug",   action="store_true", help="Enable debug output")
    parser.add_argument("--server",  action="store_true", help="Start web UI server only")
    parser.add_argument("--install", action="store_true", help="Install/update dependencies")
    args = parser.parse_args()

    # ── Install mode ──────────────────────────────────────────────
    if args.install:
        install_deps()
        return

    # ── Dependency check ──────────────────────────────────────────
    missing = check_deps()
    if missing:
        print("⚠  Missing packages:", ", ".join(missing))
        print("   Run:  python run.py --install\n")
        ans = input("Install now? [y/N]: ").strip().lower()
        if ans == 'y':
            install_deps()
        else:
            print("Cannot continue without packages. Exiting.")
            sys.exit(1)

    # ── CLI extraction mode ───────────────────────────────────────
    if args.pdf:
        cmd = [PY, SYLEX, "--pdf", args.pdf]
        if args.course: cmd += ["--course", args.course]
        if args.out:    cmd += ["--out",    args.out]
        if args.hints:  cmd += ["--hints",  args.hints]
        if args.debug:  cmd.append("--debug")

        print(f"SYLEX v3.0 — {'Task 2' if args.course else 'Task 1'}")
        print(f"PDF:    {args.pdf}")
        if args.course: print(f"Course: {args.course}")
        print("─" * 50)

        result = subprocess.run(cmd)
        sys.exit(result.returncode)

    # ── Server / Web UI mode ─────────────────────────────────────
    print("╔══════════════════════════════════════════╗")
    print("║   SYLEX v3.0 — Syllabus Extraction       ║")
    print("║   Web UI starting at http://localhost:7823║")
    print("╚══════════════════════════════════════════╝")
    print()
    print("  Ctrl+C to stop the server.")
    print()
    subprocess.run([PY, SERVER, "--browser"])

if __name__ == "__main__":
    main()
