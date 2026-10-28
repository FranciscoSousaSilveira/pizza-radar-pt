"""Testes determinísticos para a fonte pública Glovo da Telepizza."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from pizza_radar.adapters.glovo_telepizza import GlovoTelepizzaAdapter, _STORE_URL
from pizza_radar.core.models import Brand, DiscountType, DispatchMethod, OfferType, StoreScope


FIXTURE = Path(__file__).parent / "fixtures" / "glovo_telepizza_lis.html"
OBSERVED_AT = datetime(2026, 10, 28, 18, 0, tzinfo=timezone.utc)


class TestGlovoTelepizzaAdapter(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = GlovoTelepizzaAdapter()
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_parse_only_visible_promotional_tiles(self) -> None:
        parsed = self.adapter.parse(self.html)

        self.assertEqual([item["title"] for item in parsed], ["Funny Bacon Média", "4 Queijos Média"])
        self.assertEqual(parsed[0]["price_cents"], 2095)
        self.assertEqual(parsed[0]["pizza_count"], 2)
        self.assertEqual(parsed[1]["discount_percentage"], 25.0)

    def test_adapt_keeps_the_glovo_checkout_without_inventing_a_store(self) -> None:
        item = self.adapter.parse(self.html)[0]
        promo = self.adapter.adapt(item, OBSERVED_AT)

        self.assertIs(promo.vendor, Brand.TELEPIZZA)
        self.assertEqual(promo.source_url, _STORE_URL)
        self.assertEqual(promo.dispatch_methods, [DispatchMethod.DELIVERY])
        self.assertIs(promo.store_scope, StoreScope.UNKNOWN)
        self.assertEqual(promo.store_ids, [])
        self.assertEqual(promo.store_names, [])
        self.assertIs(promo.discount_type, DiscountType.X_FOR_Y)

    def test_non_pizza_two_for_one_does_not_gain_a_pizza_count(self) -> None:
        promo = self.adapter.adapt(
            {
                "id": "glovo-haagen-dazs",
                "title": "Haagen-Dazs Strawb. Cheesecake",
                "description": "2x1 — promoção observada na Glovo.",
                "conditions": "2x1. Preço e disponibilidade confirmados na Glovo para Lisboa.",
                "price_cents": 395,
                "discount_percentage": None,
                "pizza_count": None,
            },
            OBSERVED_AT,
        )

        self.assertIsNone(promo.pizza_count)
        self.assertIs(promo.offer_type, OfferType.UNKNOWN)

    def test_fetch_promotions_uses_a_single_public_page(self) -> None:
        with patch.object(self.adapter, "fetch_raw", return_value=self.html) as fetch_raw:
            promos = self.adapter.fetch_promotions()

        fetch_raw.assert_called_once()
        self.assertEqual(len(promos), 2)
        self.assertEqual({promo.source_url for promo in promos}, {_STORE_URL})
