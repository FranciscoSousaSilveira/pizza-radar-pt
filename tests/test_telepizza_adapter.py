"""Testes unitários determinísticos para o TelepizzaAdapter."""

from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from pizza_radar.adapters.telepizza import (
    DEFAULT_PROMOTION_IDS,
    TelepizzaAdapter,
    _extract_cents_from_text,
    _extract_discount_percentage,
)
from pizza_radar.core.adapter import NetworkError, ParseError
from pizza_radar.core.models import (
    Brand,
    DiscountType,
    DispatchMethod,
    OfferType,
    StoreScope,
    Weekday,
)
from pizza_radar.core.validator import validate_promo

_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_html(filename: str) -> str:
    path = os.path.join(_FIXTURES_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return f.read()


def _load_json_fixture(filename: str) -> dict:
    path = os.path.join(_FIXTURES_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return json.loads(f.read(), parse_float=Decimal)


def _observed_at() -> datetime:
    return datetime(2026, 9, 28, 15, 0, 0, tzinfo=timezone.utc)


class TestTelepizzaAdapter(unittest.TestCase):
    """Testa o adaptador da Telepizza com dados SCAPI e suporte HTML legado."""

    def setUp(self) -> None:
        self.adapter = TelepizzaAdapter()
        self.html_content = _load_html("telepizza_promocoes.html")
        self.scapi_data = _load_json_fixture("telepizza_scapi.json")

    def test_extract_cents_helper(self) -> None:
        """Extrai cêntimos com suporte a &euro; e vírgula."""
        self.assertEqual(_extract_cents_from_text("1 Média Descomplicada por 10€"), 1000)
        self.assertEqual(_extract_cents_from_text("Média ao Balcão por 5,95€"), 595)
        self.assertEqual(_extract_cents_from_text("Preço de 12,50&euro;"), 1250)
        self.assertIsNone(_extract_cents_from_text("2x1 em Todas as Pizzas"))

    def test_extract_discount_percentage_helper(self) -> None:
        """Extrai percentagem de desconto por regex."""
        self.assertEqual(_extract_discount_percentage("30% desconto em Pizzas"), 30.0)
        self.assertEqual(_extract_discount_percentage("-55% em 3 Pizzas Médias"), 55.0)
        self.assertIsNone(_extract_discount_percentage("Preço fixo 10€"))

    def test_parse_scapi_fixture(self) -> None:
        """Extrai todas as 20 campanhas oficiais do payload SCAPI."""
        parsed = self.adapter.parse_scapi(self.scapi_data)
        self.assertEqual(len(parsed), 20)

        # 2x1 Médias e Familiares
        p_2x1 = next(p for p in parsed if p["id"] == "2x1_MedFam")
        self.assertEqual(p_2x1["title"], "2x1 Médias e Familiares")
        self.assertIn("delivery", p_2x1["channels"])
        self.assertIn("takeaway", p_2x1["channels"])
        self.assertEqual(p_2x1["days_of_week"], [Weekday.TUESDAY])
        self.assertEqual(p_2x1["pizza_count"], 2)

        # MMINDTSTK - Meu Menu Individual por 5,95€
        p_menu = next(p for p in parsed if p["id"] == "MMINDTSTK")
        self.assertEqual(p_menu["price_cents"], 595)
        self.assertEqual(p_menu["channels"], ["takeaway"])
        self.assertEqual(p_menu["valid_from"], "2026-08-18T23:00Z")
        self.assertEqual(p_menu["valid_until"], "2026-10-19T22:45Z")

        # 55_NC - -55% em 3 Pizzas Médias
        p_55 = next(p for p in parsed if p["id"] == "55_NC")
        self.assertEqual(p_55["discount_percentage"], 55.0)
        self.assertEqual(p_55["pizza_count"], 3)

    def test_adapt_scapi_all_promotions_and_classification(self) -> None:
        """Converte todas as campanhas SCAPI em UnifiedPromo e valida tipagem e classificação."""
        parsed = self.adapter.parse_scapi(self.scapi_data)
        all_promos = []
        for it in parsed:
            adapted = self.adapter.adapt(it, _observed_at())
            self.assertIsInstance(adapted, list)
            all_promos.extend(adapted)

        # Confirma que mais de 20 promos são geradas (devido a canais delivery + takeaway)
        self.assertGreater(len(all_promos), 20)

        for p in all_promos:
            validated = validate_promo(p)
            self.assertEqual(validated.vendor, Brand.TELEPIZZA)
            self.assertEqual(validated.store_scope, StoreScope.UNKNOWN)
            self.assertEqual(validated.location_scope, "Lisboa")

        # Classificação estrita de produtos NON_PIZZA
        drinks = [p for p in all_promos if "2BEBGARX" in p.id or "2BEB33K" in p.id]
        self.assertGreater(len(drinks), 0)
        for d in drinks:
            self.assertEqual(d.offer_type, OfferType.NON_PIZZA)

        ice_cream = [p for p in all_promos if "2x1_Gel" in p.id]
        self.assertGreater(len(ice_cream), 0)
        for ic in ice_cream:
            self.assertEqual(ic.offer_type, OfferType.NON_PIZZA)

        chicken = [p for p in all_promos if "BUCKETSLK" in p.id]
        self.assertGreater(len(chicken), 0)
        for ck in chicken:
            self.assertEqual(ck.offer_type, OfferType.NON_PIZZA)

    def test_fetch_promotions_scapi_full(self) -> None:
        """fetch_promotions() recolhe, adapta e valida com cobertura FEATURED."""
        with patch.object(self.adapter, "fetch_slas_token", return_value="mock-access-token"), \
             patch.object(self.adapter, "fetch_scapi_promotions", return_value=self.scapi_data):
            promos = self.adapter.fetch_promotions()

        self.assertGreater(len(promos), 20)
        self.assertEqual(self.adapter.coverage_level, "FEATURED")
        self.assertEqual(
            self.adapter.coverage_note,
            "Campanhas principais sincronizadas via API oficial Salesforce (amostra de 20 campanhas ativas)",
        )

    def test_discover_promotion_ids_with_dynamic_hits(self) -> None:
        """Descoberta dinâmica extrai e deduplica IDs quando productPromotions está presente."""
        page1 = {
            "total": 3,
            "hits": [
                {"productId": "prod1", "productPromotions": [{"promotionId": "PROMO_A"}, {"promotionId": "PROMO_B"}]},
                {"productId": "prod2", "promotions": [{"id": "PROMO_B"}, {"id": "PROMO_C"}]},
            ]
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(page1).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            ids = self.adapter.discover_promotion_ids(token="mock-token", max_pages=1)

        self.assertEqual(ids, ["PROMO_A", "PROMO_B", "PROMO_C"])

    def test_discover_promotion_ids_fallback_on_empty(self) -> None:
        """Fallback para DEFAULT_PROMOTION_IDS quando o catálogo não tem productPromotions."""
        page_empty = {
            "total": 50,
            "hits": [
                {"productId": "pizza1", "productName": "Pizza Atlantica"},
                {"productId": "pizza2", "productName": "Pizza Tuna"},
            ]
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(page_empty).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            ids = self.adapter.discover_promotion_ids(token="mock-token", max_pages=1)

        self.assertEqual(ids, DEFAULT_PROMOTION_IDS)

    def test_fetch_scapi_promotions_chunking(self) -> None:
        """fetch_scapi_promotions divide mais de 50 IDs em lotes de 50 e unifica as respostas."""
        fake_ids = [f"PROMO_{i}" for i in range(75)]
        chunk1 = {"data": [{"id": f"PROMO_{i}", "name": f"P {i}"} for i in range(50)]}
        chunk2 = {"data": [{"id": f"PROMO_{i}", "name": f"P {i}"} for i in range(50, 75)]}

        with patch("urllib.request.urlopen") as mock_urlopen:
            resp1 = MagicMock()
            resp1.read.return_value = json.dumps(chunk1).encode("utf-8")
            resp2 = MagicMock()
            resp2.read.return_value = json.dumps(chunk2).encode("utf-8")
            mock_urlopen.return_value.__enter__.side_effect = [resp1, resp2]

            result = self.adapter.fetch_scapi_promotions(token="mock-token", promo_ids=fake_ids)

        self.assertEqual(result["total"], 75)
        self.assertEqual(len(result["data"]), 75)

    def test_parse_html_fixture(self) -> None:
        """Extrai os 3 cartões promocionais do HTML legado."""
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

    def test_error_propagation(self) -> None:
        """NetworkError e ParseError propagam com vendor=TELEPIZZA."""
        with patch.object(self.adapter, "fetch_slas_token", side_effect=NetworkError("Network down", vendor=Brand.TELEPIZZA)):
            with self.assertRaises(NetworkError) as ctx:
                self.adapter.fetch_promotions()
            self.assertEqual(ctx.exception.vendor, Brand.TELEPIZZA)


if __name__ == "__main__":
    unittest.main()
