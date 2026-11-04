"""Keep the local server's static allowlist in sync with the page shell."""

import re
import unittest
from pathlib import Path

from sylex_server import STATIC_FILES


ROOT = Path(__file__).resolve().parents[1]


class StaticAssetTests(unittest.TestCase):
    def test_page_assets_are_served_by_local_server(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        references = re.findall(r'(?:href|src)="([^"]+\.(?:css|js)(?:\?[^"]*)?)"', html)
        self.assertTrue(references)
        for reference in references:
            asset = reference.split("?", 1)[0]
            with self.subTest(asset=asset):
                self.assertIn(asset, STATIC_FILES)
                self.assertTrue((ROOT / asset).is_file())


if __name__ == "__main__":
    unittest.main()
