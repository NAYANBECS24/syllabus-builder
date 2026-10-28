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
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SYLEX    = os.path.join(BASE_DIR, "sylex.py")
SERVER   = os.path.join(BASE_DIR, "sylex_server.py")
SERVER_PID_FILE = os.path.join(BASE_DIR, ".sylex-server.pid")

# ── Find Python ────────────────────────────────────────────────────
def find_python():
    candidates = [
        sys.executable,
        "python", "python3", "py",
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

def _read_server_pid():
    try:
        with open(SERVER_PID_FILE, "r", encoding="utf-8") as pid_handle:
            pid = int(pid_handle.read().strip())
        return pid if pid > 0 else None
    except (OSError, TypeError, ValueError):
        return None

def _process_exists(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def _process_command(pid):
    """Read a process command without requiring third-party process libraries."""
    if os.name == "nt":
        command = (
            "$process = Get-CimInstance Win32_Process -Filter 'ProcessId = "
            + str(int(pid))
            + "'; if ($process) { $process.CommandLine }"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=5,
        )
    else:
        result = subprocess.run(
            ["ps", "-p", str(int(pid)), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=5,
        )
    return result.stdout.strip() if result.returncode == 0 else ""

def _is_sylex_server(pid):
    command = os.path.normcase(_process_command(pid)).replace("/", os.sep).replace("\\", os.sep)
    server_path = os.path.normcase(os.path.abspath(SERVER))
    return bool(command and server_path in command)

def _remove_stale_pid_file(expected_pid=None):
    try:
        if expected_pid is not None and _read_server_pid() != expected_pid:
            return
        os.remove(SERVER_PID_FILE)
    except FileNotFoundError:
        pass

def stop_previous_server():
    """Stop only the prior server recorded by this project, never an arbitrary port owner."""
    pid = _read_server_pid()
    if not pid:
        return False
    if not _process_exists(pid) or not _is_sylex_server(pid):
        _remove_stale_pid_file(pid)
        return False
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if result.returncode != 0 and _process_exists(pid):
            raise RuntimeError("The previous SYLEX server could not be stopped")
    else:
        import signal
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 4
    while _process_exists(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    if _process_exists(pid):
        raise RuntimeError("The previous SYLEX server did not exit in time")
    _remove_stale_pid_file(pid)
    return True

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
    try:
        if stop_previous_server():
            print("  Previous SYLEX session closed. Starting a fresh session...\n")
    except RuntimeError as exc:
        print(f"  ERROR: {exc}")
        sys.exit(1)
    server_cmd = [PY, SERVER]
    if not args.server:
        server_cmd.append("--browser")
    subprocess.run(server_cmd)

if __name__ == "__main__":
    main()
