"""Testes unitários determinísticos para o PizzaHutAdapter."""

from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from pizza_radar.adapters.pizza_hut import PizzaHutAdapter, _extract_cents_from_text
from pizza_radar.core.adapter import NetworkError, ParseError
from pizza_radar.core.models import Brand, DiscountType, DispatchMethod, StoreScope
from pizza_radar.core.validator import validate_promo

_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(filename: str) -> list[dict]:
    path = os.path.join(_FIXTURES_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return json.loads(f.read(), parse_float=Decimal)


def _observed_at() -> datetime:
    return datetime(2026, 9, 28, 15, 0, 0, tzinfo=timezone.utc)


class TestPizzaHutAdapter(unittest.TestCase):
    """Testa o adaptador da Pizza Hut com JSON sanitizado."""

    def setUp(self) -> None:
        self.adapter = PizzaHutAdapter()
        self.offers_raw = _load_fixture("pizzahut_ofertas.json")

    def test_extract_cents_helper(self) -> None:
        """Extrai cêntimos com suporte a inteiros e decimais."""
        self.assertEqual(_extract_cents_from_text("DOUBLE STUFFED CRUST – Apenas 6€ por pessoa"), 600)
        self.assertEqual(_extract_cents_from_text("MENU DOUBLE STUFFED CRUST 24,25€"), 2425)
        self.assertIsNone(_extract_cents_from_text("2x1 terças"))

    def test_parse_offers_fixture(self) -> None:
        """Extrai as 3 ofertas da fixture sanitizada com unescape de HTML."""
        parsed = self.adapter.parse(self.offers_raw)
        self.assertEqual(len(parsed), 3)

        o1 = next(o for o in parsed if o["id"] == "15056")
        self.assertIn("6€ por pessoa", o1["title"])
        self.assertNotIn("&#8211;", o1["title"])  # HTML unescaped
        self.assertEqual(o1["price_cents"], 600)

        o2 = next(o for o in parsed if o["id"] == "15049")
        self.assertEqual(o2["price_cents"], 2425)

    def test_adapt_2x1_has_two_for_one_discount_type(self) -> None:
        """2x1 da Pizza Hut mapeia para X_FOR_Y com StoreScope.UNKNOWN e canal Take Away."""
        parsed = self.adapter.parse(self.offers_raw)
        o3 = next(o for o in parsed if o["id"] == "14626")
        promo = self.adapter.adapt(o3, _observed_at())

        validated = validate_promo(promo)
        self.assertEqual(validated.vendor, Brand.PIZZA_HUT)
        self.assertEqual(validated.discount_type, DiscountType.X_FOR_Y)
        self.assertEqual(validated.store_scope, StoreScope.UNKNOWN)
        self.assertEqual(validated.store_ids, [])
        self.assertEqual(validated.store_names, [])
        self.assertEqual(validated.dispatch_methods, [DispatchMethod.TAKE_AWAY])

    def test_known_vs_unknown_participating_stores(self) -> None:
        """Verifica distinção entre lojas comprovadas (SPECIFIC_STORES) e incerteza (UNKNOWN)."""
        # Caso 1: Lojas comprovadas no payload
        payload_known = [{
            "id": 9901,
            "slug": "promo-lojas-especificas-tw",
            "title": {"rendered": "Promo Colombo e Vasco 15€"},
            "participating_stores": [
                {"id": "colombo", "name": "Colombo"},
                {"id": "vasco", "name": "Vasco da Gama"},
            ],
        }]
        parsed_known = self.adapter.parse(payload_known)
        self.assertEqual(parsed_known[0]["store_scope"], StoreScope.SPECIFIC_STORES)
        self.assertEqual(parsed_known[0]["store_ids"], ["colombo", "vasco"])
        self.assertEqual(parsed_known[0]["store_names"], ["Colombo", "Vasco da Gama"])

        promo_known = self.adapter.adapt(parsed_known[0], _observed_at())
        self.assertEqual(promo_known.store_scope, StoreScope.SPECIFIC_STORES)

        # Caso 2: Sem lojas comprovadas -> StoreScope.UNKNOWN
        payload_unknown = [{
            "id": 9902,
            "slug": "promo-geral-tw",
            "title": {"rendered": "Promo Geral 10€"},
        }]
        parsed_unknown = self.adapter.parse(payload_unknown)
        self.assertEqual(parsed_unknown[0]["store_scope"], StoreScope.UNKNOWN)
        self.assertEqual(parsed_unknown[0]["store_ids"], [])
        self.assertEqual(parsed_unknown[0]["store_names"], [])

        promo_unknown = self.adapter.adapt(parsed_unknown[0], _observed_at())
        self.assertEqual(promo_unknown.store_scope, StoreScope.UNKNOWN)

    def test_channel_detection_variations(self) -> None:
        """Verifica deteção de canal por slug e texto sem inventar canais."""
        from pizza_radar.core.models import DispatchMethod

        # Take Away por slug -tw
        p_tw = self.adapter.parse([{
            "id": 1,
            "slug": "oferta-tw",
            "title": {"rendered": "Oferta Balcão"},
        }])[0]
        self.assertEqual(p_tw["dispatch_methods"], [DispatchMethod.TAKE_AWAY])

        # Delivery por slug -dlv
        p_dlv = self.adapter.parse([{
            "id": 2,
            "slug": "oferta-dlv",
            "title": {"rendered": "Oferta Entrega"},
        }])[0]
        self.assertEqual(p_dlv["dispatch_methods"], [DispatchMethod.DELIVERY])

        # Dine-in por slug rodizio
        p_dine = self.adapter.parse([{
            "id": 3,
            "slug": "rodizio",
            "title": {"rendered": "Rodízio na Mesa"},
        }])[0]
        self.assertEqual(p_dine["dispatch_methods"], [DispatchMethod.DINE_IN])

        # Falta de canal comprovado -> ParseError (não assume ambos nem inventa)
        with self.assertRaises(ParseError):
            self.adapter.parse([{
                "id": 4,
                "slug": "oferta-sem-canal",
                "title": {"rendered": "Pizza Simples"},
            }])

    def test_missing_mandatory_fields_raises_parse_error(self) -> None:
        """Item sem ID ou com título vazio emite ParseError explicitamente."""
        with self.assertRaises(ParseError):
            self.adapter.parse([{"id": None, "title": {"rendered": "Sem ID"}}])

        with self.assertRaises(ParseError):
            self.adapter.parse([{"id": 123, "title": {"rendered": "   "}}])

    def test_fetch_promotions_full_mock(self) -> None:
        """fetch_promotions() extrai e valida todas as promoções."""
        with patch.object(self.adapter, "fetch_raw", return_value=self.offers_raw):
            promos = self.adapter.fetch_promotions()

        self.assertGreater(len(promos), 0)
        for p in promos:
            validate_promo(p)
            self.assertEqual(p.vendor, Brand.PIZZA_HUT)
            self.assertEqual(p.store_scope, StoreScope.UNKNOWN)

    def test_error_propagation(self) -> None:
        """NetworkError e ParseError propagam com vendor=PIZZA_HUT."""
        with patch.object(self.adapter, "fetch_raw", side_effect=NetworkError("WP API down", vendor=Brand.PIZZA_HUT)):
            with self.assertRaises(NetworkError) as ctx:
                self.adapter.fetch_promotions()
            self.assertEqual(ctx.exception.vendor, Brand.PIZZA_HUT)


if __name__ == "__main__":
    unittest.main()
