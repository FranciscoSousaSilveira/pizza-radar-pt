"""Testes unitários determinísticos para o TelepizzaAdapter."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from pizza_radar.adapters.telepizza import TelepizzaAdapter, _extract_cents_from_text
from pizza_radar.core.adapter import NetworkError, ParseError
from pizza_radar.core.models import Brand, DiscountType, DispatchMethod, StoreScope
from pizza_radar.core.validator import validate_promo

_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_html(filename: str) -> str:
    path = os.path.join(_FIXTURES_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return f.read()


def _observed_at() -> datetime:
    return datetime(2026, 9, 28, 15, 0, 0, tzinfo=timezone.utc)


class TestTelepizzaAdapter(unittest.TestCase):
    """Testa o adaptador da Telepizza com HTML sanitizado."""

    def setUp(self) -> None:
        self.adapter = TelepizzaAdapter()
        self.html_content = _load_html("telepizza_promocoes.html")

    def test_extract_cents_helper(self) -> None:
        """Extrai cêntimos com suporte a &euro; e vírgula."""
        self.assertEqual(_extract_cents_from_text("1 Média Descomplicada por 10€"), 1000)
        self.assertEqual(_extract_cents_from_text("Média ao Balcão por 5,95€"), 595)
        self.assertEqual(_extract_cents_from_text("Preço de 12,50&euro;"), 1250)
        self.assertIsNone(_extract_cents_from_text("2x1 em Todas as Pizzas"))

    def test_parse_html_fixture(self) -> None:
        """Extrai os 3 cartões promocionais do HTML."""
        parsed = self.adapter.parse(self.html_content)
        self.assertEqual(len(parsed), 3)

        p1 = next(c for c in parsed if c["id"] == "2ADMMK")
        self.assertEqual(p1["title"], "1 Média Descomplicada por 10€")
        self.assertEqual(p1["price_cents"], 1000)
        self.assertIn("delivery", p1["channels"])
        self.assertIn("takeaway", p1["channels"])

        p2 = next(c for c in parsed if c["id"] == "Med595_TK")
        self.assertEqual(p2["price_cents"], 595)
        self.assertEqual(p2["channels"], ["takeaway"])

        p3 = next(c for c in parsed if c["id"] == "2X1_NC")
        self.assertIsNone(p3["price_cents"])

    def test_adapt_2x1_has_two_for_one_discount_type(self) -> None:
        """Oferta com 2x1 no título mapeia para DiscountType.X_FOR_Y com StoreScope.UNKNOWN."""
        parsed = self.adapter.parse(self.html_content)
        p3 = next(c for c in parsed if c["id"] == "2X1_NC")
        promo = self.adapter.adapt(p3, _observed_at(), channel="delivery")

        validated = validate_promo(promo)
        self.assertEqual(validated.vendor, Brand.TELEPIZZA)
        self.assertEqual(validated.discount_type, DiscountType.X_FOR_Y)
        self.assertEqual(validated.store_scope, StoreScope.UNKNOWN)
        self.assertEqual(validated.store_ids, [])
        self.assertEqual(validated.store_names, [])

    def test_attribute_order_permutations(self) -> None:
        """Parser HTML extrai os dados independentemente da ordem em que os atributos aparecem."""
        html_permuted = """
        <div class="col-12 offer-tile__wrap" data-tab-content="takeaway">
          <a data-detail="Massa Fofa com 3 ing."
             data-name="Pizza Especial 12€"
             data-img-url="https://images.telepizza.pt/p12.png"
             class="offer-tile__view-more__btn-icon"
             data-id="PERM_01">
             Ver Mais
          </a>
        </div>
        """
        parsed = self.adapter.parse(html_permuted)
        self.assertEqual(len(parsed), 1)
        card = parsed[0]
        self.assertEqual(card["id"], "PERM_01")
        self.assertEqual(card["title"], "Pizza Especial 12€")
        self.assertEqual(card["description"], "Massa Fofa com 3 ing.")
        self.assertEqual(card["price_cents"], 1200)
        self.assertEqual(card["channels"], ["takeaway"])
        self.assertEqual(card["image_url"], "https://images.telepizza.pt/p12.png")

    def test_missing_mandatory_fields_raises_parse_error(self) -> None:
        """Cartão sem ID ou sem título emite ParseError explicitamente."""
        html_missing_id = """
        <div class="col-12 offer-tile__wrap" data-tab-content="takeaway">
          <a class="offer-tile__view-more__btn-icon" data-id="" data-name="Sem ID"></a>
        </div>
        """
        with self.assertRaises(ParseError):
            self.adapter.parse(html_missing_id)

        html_missing_name = """
        <div class="col-12 offer-tile__wrap" data-tab-content="takeaway">
          <a class="offer-tile__view-more__btn-icon" data-id="ID_ONLY" data-name="  "></a>
        </div>
        """
        with self.assertRaises(ParseError):
            self.adapter.parse(html_missing_name)

    def test_unevidenced_channel_raises_parse_error(self) -> None:
        """Oferta sem nenhuma evidência de delivery ou takeaway emite ParseError em vez de inventar."""
        html_no_channel = """
        <div class="col-12 offer-tile__wrap" data-tab-content="">
          <a class="offer-tile__view-more__btn-icon" data-id="NO_CH" data-name="Promo Indefinida" data-detail="Sem menção"></a>
        </div>
        """
        with self.assertRaises(ParseError):
            self.adapter.parse(html_no_channel)

    def test_fetch_promotions_full_mock(self) -> None:
        """fetch_promotions() extrai e valida todas as promoções."""
        with patch.object(self.adapter, "fetch_raw", return_value=self.html_content):
            promos = self.adapter.fetch_promotions()

        self.assertGreater(len(promos), 0)
        for p in promos:
            validate_promo(p)
            self.assertEqual(p.vendor, Brand.TELEPIZZA)
            self.assertEqual(p.store_scope, StoreScope.UNKNOWN)

    def test_error_propagation(self) -> None:
        """NetworkError e ParseError propagam com vendor=TELEPIZZA."""
        with patch.object(self.adapter, "fetch_raw", side_effect=NetworkError("Network down", vendor=Brand.TELEPIZZA)):
            with self.assertRaises(NetworkError) as ctx:
                self.adapter.fetch_promotions()
            self.assertEqual(ctx.exception.vendor, Brand.TELEPIZZA)


if __name__ == "__main__":
    unittest.main()
