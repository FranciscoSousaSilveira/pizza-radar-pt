"""Testes de conformidade e integridade da interface web do Pizza Radar PT."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"
SCREENSHOTS_DIR = ROOT_DIR / "docs" / "screenshots"


class TestWebInterfaceIntegrity(unittest.TestCase):
    """Verifica a integridade dos ficheiros da interface web e do contrato do snapshot."""

    def test_web_static_files_exist(self) -> None:
        self.assertTrue((WEB_DIR / "index.html").exists(), "web/index.html deve existir")
        self.assertTrue((WEB_DIR / "styles.css").exists(), "web/styles.css deve existir")
        self.assertTrue((WEB_DIR / "app.js").exists(), "web/app.js deve existir")
        self.assertTrue((WEB_DIR / "data" / "promotions.json").exists(), "web/data/promotions.json deve existir")

    def test_html_accessibility_and_landmarks(self) -> None:
        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('role="banner"', html)
        self.assertIn('role="main"', html)
        self.assertIn('role="contentinfo"', html)
        self.assertIn('class="skip-link"', html)
        self.assertIn('id="main-content"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('tab-lowest-price', html)
        self.assertIn('tab-highest-discount', html)
        self.assertIn('tab-unit-price', html)
        self.assertIn('tab-recently-observed', html)
        # Sem formulários de checkout nem inputs de pagamento
        self.assertNotIn("<form", html.lower())
        self.assertNotIn('type="password"', html.lower())
        self.assertNotIn("card-number", html.lower())
        self.assertNotIn("cvv", html.lower())
        self.assertNotIn("stripe", html.lower())
        self.assertNotIn("paypal", html.lower())

    def test_snapshot_schema_conformance(self) -> None:
        json_path = WEB_DIR / "data" / "promotions.json"
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data.get("schema_version"), "1.0.0")
        self.assertEqual(data.get("location_scope"), "Lisboa")
        self.assertIn("stats", data)
        self.assertIn("groups", data)
        self.assertGreater(len(data["groups"]), 0)

        required_group_fields = {
            "persistent_id",
            "vendor",
            "title",
            "dispatch_methods",
            "store_scope",
            "min_price_cents",
            "display_price_label",
            "source_url",
            "variants",
        }
        for group in data["groups"]:
            for field_name in required_group_fields:
                self.assertIn(field_name, group, f"Campo {field_name} deve constar no grupo {group.get('persistent_id')}")

    def test_screenshots_exist_and_non_empty(self) -> None:
        desktop_png = SCREENSHOTS_DIR / "desktop_view.png"
        mobile_png = SCREENSHOTS_DIR / "mobile_view.png"
        self.assertTrue(desktop_png.exists(), "desktop_view.png deve existir")
        self.assertTrue(mobile_png.exists(), "mobile_view.png deve existir")
        self.assertGreater(desktop_png.stat().st_size, 10000, "desktop_view.png não pode estar vazio")
        self.assertGreater(mobile_png.stat().st_size, 10000, "mobile_view.png não pode estar vazio")


if __name__ == "__main__":
    unittest.main()
