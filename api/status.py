"""Use the same capability report locally and in Vercel."""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sylex_server import Handler


class handler(Handler):
    def do_GET(self):
        self.path = "/api/status"
        super().do_GET()

    def do_POST(self):
        self.send_json({"error": "Use GET /api/status"}, 405)
