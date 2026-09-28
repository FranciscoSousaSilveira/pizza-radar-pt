"""Testes unitários determinísticos para o DominosAdapter."""

from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from pizza_radar.adapters.dominos import (
    DominosAdapter,
    _extract_cents_from_text,
    _extract_discount_percentage,
)
from pizza_radar.core.adapter import NetworkError, ParseError
from pizza_radar.core.models import Brand, DispatchMethod, Weekday
from pizza_radar.core.validator import validate_promo

_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(filename: str) -> dict:
    path = os.path.join(_FIXTURES_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return json.loads(f.read(), parse_float=Decimal)


def _observed_at() -> datetime:
    return datetime(2026, 9, 28, 15, 0, 0, tzinfo=timezone.utc)


class TestDominosAdapter(unittest.TestCase):
    """Testa o adaptador da Domino's Pizza com dados sanitizados."""

    def setUp(self) -> None:
        self.adapter = DominosAdapter()
        self.delivery_raw = _load_fixture("dominos_delivery.json")
        self.carryout_raw = _load_fixture("dominos_carryout.json")

    def test_extract_cents_helper(self) -> None:
        """Extrai cêntimos com exatidão de strings com vírgula, ponto e inteiros."""
        self.assertEqual(_extract_cents_from_text("MÉDIA DESDE 10,95€"), 1095)
        self.assertEqual(_extract_cents_from_text("Grande desde 12€ cada"), 1200)
        self.assertEqual(_extract_cents_from_text("MENU FAMÍLIA GRANDES | Desde 27€"), 2700)
        self.assertIsNone(_extract_cents_from_text("Sem preço anunciado"))

    def test_extract_discount_percentage_helper(self) -> None:
        """Extrai percentagem de desconto de títulos promocionais."""
        self.assertEqual(_extract_discount_percentage("SEGUNDAS A DOBRAR | 40% DESCONTO"), 40.0)
        self.assertIsNone(_extract_discount_percentage("MÉDIA DESDE 10,95€"))

    def test_parse_delivery_fixture(self) -> None:
        """Parse de fixture de entrega extrai os 4 combos."""
        parsed = self.adapter.parse(self.delivery_raw, delivery_method="D")
        self.assertEqual(len(parsed), 4)

        combo_1095 = next(c for c in parsed if c["id"] == "2420")
        self.assertEqual(combo_1095["price_cents"], 1095)
        self.assertEqual(combo_1095["delivery_method"], "D")

        combo_segunda = next(c for c in parsed if c["id"] == "2434")
        self.assertEqual(combo_segunda["discount_percentage"], 40.0)
        self.assertIsNone(combo_segunda["price_cents"])

    def test_adapt_delivery_promo_passes_validation(self) -> None:
        """Adaptação gera UnifiedPromo validável pelo contrato canónico."""
        parsed = self.adapter.parse(self.delivery_raw, delivery_method="D")
        combo = parsed[0]
        promo = self.adapter.adapt(combo, _observed_at())

        validated = validate_promo(promo)
        self.assertEqual(validated.vendor, Brand.DOMINOS)
        self.assertEqual(validated.id, "dom_2420_delivery")
        self.assertEqual(validated.price_cents, 1095)
        self.assertEqual(validated.dispatch_methods, [DispatchMethod.DELIVERY])

    def test_adapt_segundas_a_dobrar_has_monday_weekday(self) -> None:
        """Promoção 'Segundas a Dobrar' é mapeada para Weekday.MONDAY."""
        parsed = self.adapter.parse(self.delivery_raw, delivery_method="D")
        combo = next(c for c in parsed if c["id"] == "2434")
        promo = self.adapter.adapt(combo, _observed_at())

        self.assertEqual(promo.days_of_week, [Weekday.MONDAY])

    def test_fetch_promotions_full_mock(self) -> None:
        """fetch_promotions() integra Delivery e Take Away sem duplicados."""
        def mock_fetch(delivery_method: str = "D", store_id: str = "140", timeout: float = 15.0) -> dict:
            return self.delivery_raw if delivery_method == "D" else self.carryout_raw

        with patch.object(self.adapter, "fetch_raw", side_effect=mock_fetch):
            promos = self.adapter.fetch_promotions()

        self.assertGreater(len(promos), 0)
        for p in promos:
            validate_promo(p)
            self.assertEqual(p.vendor, Brand.DOMINOS)

    def test_error_propagation(self) -> None:
        """NetworkError e ParseError propagam com vendor correto."""
        with patch.object(self.adapter, "fetch_raw", side_effect=NetworkError("Timeout", vendor=Brand.DOMINOS)):
            with self.assertRaises(NetworkError) as ctx:
                self.adapter.fetch_promotions()
            self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)


if __name__ == "__main__":
    unittest.main()
