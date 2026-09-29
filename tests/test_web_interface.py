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

    def test_demo_mode_displays_explicit_warning(self) -> None:
        """Em modo demo, a interface deve exibir explicitamente o aviso no topo."""
        json_path = WEB_DIR / "data" / "promotions.json"
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("data_mode"), "demo", "O snapshot estático de desenvolvimento deve ter data_mode='demo'")

        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn("data-mode-banner", html, "index.html deve conter o elemento do banner de modo de dados")
        self.assertIn(
            "Dados de demonstração — atualização automática ainda não ativa",
            html,
            "index.html deve conter o texto exato do aviso de modo de demonstração",
        )

        js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
        self.assertIn("handleDataMode", js)
        self.assertIn("Dados de demonstração — atualização automática ainda não ativa", js)

    def test_demo_mode_does_not_assert_automatic_updates(self) -> None:
        """Em modo demo, o cabeçalho não pode afirmar que está atualizado 2x ao dia."""
        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        # O HTML estático inicial não pode conter a alegação de 2x ao dia no cabeçalho
        header_part = html[html.find('<header'):html.find('</header>')]
        self.assertNotIn(
            "Atualizado 2x ao dia",
            header_part,
            "O cabeçalho estático não pode afirmar 'Atualizado 2x ao dia' no modo demo",
        )

        js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
        # Confirma que só em modo 'live' é exibido 'Atualizado 2x ao dia'
        self.assertIn("if (isLive)", js)

    def test_segundas_a_dobrar_not_interpreted_as_two_pizzas(self) -> None:
        """A promoção 'Segundas a Dobrar' é um desconto percentual e não pode ser tratada como 2 pizzas."""
        json_path = WEB_DIR / "data" / "promotions.json"
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        segundas_group = next(
            (g for g in data["groups"] if "SEGUNDAS A DOBRAR" in g.get("title", "")),
            None,
        )
        self.assertIsNotNone(segundas_group, "Grupo SEGUNDAS A DOBRAR deve existir na fixture")
        self.assertIsNone(segundas_group.get("pizza_count"), "pizza_count de SEGUNDAS A DOBRAR deve ser null")
        self.assertEqual(segundas_group.get("pizza_size"), "UNKNOWN", "pizza_size de SEGUNDAS A DOBRAR deve ser UNKNOWN")
        self.assertFalse(
            segundas_group.get("is_comparable_for_unit_price"),
            "SEGUNDAS A DOBRAR não pode ter is_comparable_for_unit_price=True",
        )
        self.assertIsNone(
            segundas_group.get("min_price_per_pizza_cents"),
            "min_price_per_pizza_cents deve ser null para SEGUNDAS A DOBRAR",
        )

    def test_menu_familia_grandes_has_two_large_pizzas(self) -> None:
        """MENU FAMÍLIA GRANDES que comprova 2 pizzas grandes deve usar LARGE e nunca MEDIUM."""
        json_path = WEB_DIR / "data" / "promotions.json"
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        familia_group = next(
            (g for g in data["groups"] if "MENU FAMÍLIA GRANDES" in g.get("title", "")),
            None,
        )
        self.assertIsNotNone(familia_group, "Grupo MENU FAMÍLIA GRANDES deve existir na fixture")
        self.assertEqual(familia_group.get("pizza_count"), 2, "pizza_count deve ser 2")
        self.assertEqual(familia_group.get("pizza_size"), "LARGE", "pizza_size deve ser LARGE")
        self.assertNotEqual(familia_group.get("pizza_size"), "MEDIUM", "pizza_size nunca pode ser MEDIUM")
        self.assertTrue(familia_group.get("is_comparable_for_unit_price"), "Deve ser comparável para preço unitário")
        self.assertEqual(familia_group.get("min_price_per_pizza_cents"), 1350)

    def test_unproven_offers_excluded_from_best_unit_price(self) -> None:
        """Ofertas sem contagem comprovada não podem entrar no ranking BEST_UNIT_PRICE."""
        json_path = WEB_DIR / "data" / "promotions.json"
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        for g in data["groups"]:
            if not g.get("is_comparable_for_unit_price"):
                self.assertIsNone(
                    g.get("min_price_per_pizza_cents"),
                    f"Oferta não comparável {g.get('persistent_id')} não pode ter min_price_per_pizza_cents",
                )


if __name__ == "__main__":
    unittest.main()
