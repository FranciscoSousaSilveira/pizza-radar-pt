"""Testes unitários para PapaJohnsAdapter.

Cobertura exaustiva e 100% determinística (sem dependência de rede):
  - TestMonetaryPrecision:
      * Conversão de Decimal para integer cents (7.99 -> 799, 9.45 -> 945).
      * Valores numéricos inteiros (15 -> 1500).
      * Valores em string ("7.99", "9.45", "7,99").
      * Casos de arredondamento determinístico (7.994 -> 799, 7.995 -> 800, 7.996 -> 800).
      * Valores inválidos emitem ParseError explicitamente ("abc", "", True, [], {}, nan, inf, negativo).
      * json.loads com parse_float=Decimal.
  - TestStoreDeduplicationAndAggregation:
      * Mesma oferta idêntica em três lojas -> um resultado agregando as três lojas em store_ids e store_names.
      * ID determinístico sem store_id quando unificado ("pj_{id}_{canal}").
      * Mesma oferta com preço diferente numa loja -> variantes separadas com IDs determinísticos.
      * Delivery e takeaway -> resultados estritamente separados.
  - TestHiddenOffersAndPayloadValidation:
      * Ofertas com hidden=true são ignoradas no parsing e não são publicadas.
      * Ofertas com hidden=false ou ausente são publicadas normalmente.
      * Alterações em campos obrigatórios (id, name) originam ParseError explícito.
      * Preço inválido no payload origina ParseError explícito (sem degradação silenciosa para None).
      * Tipos inválidos em pictures ou availability originam ParseError explícito.
      * pizza_count=None, pizza_size=UNKNOWN, included_items=[] (sem invenção de composição).
  - TestPapaJohnsAdapterParse:
      * Parse de fixtures sanitizadas com parse_float=Decimal.
      * Contexto de canal (delivery usa name_delivery/description_delivery para 'both').
  - TestPapaJohnsAdapterAdapt:
      * Propriedades monetárias determinísticas (price_euros, savings_amount_cents).
      * Anomalia original_price < price tratada descartando original_price_cents.
      * observed_at timezone-aware exigido.
      * validate_promo() aprovado em todos os registos.
  - TestPapaJohnsAdapterErrors:
      * Propagação de NetworkError e ParseError com vendor=PAPA_JOHNS.
  - TestPapaJohnsAdapterIntegration:
      * Execução completa de fetch_promotions() com mock de fetch_raw().
"""

from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from pizza_radar.adapters.papa_johns import (
    LISBON_STORES,
    PapaJohnsAdapter,
    _parse_availability,
    _parse_pizza_size,
    _select_image_url,
    _sort_store_ids,
    parse_price_to_cents,
)
from pizza_radar.core.adapter import NetworkError, ParseError
from pizza_radar.core.models import (
    Brand,
    DiscountType,
    DispatchMethod,
    PizzaSize,
    StoreScope,
    UnifiedPromo,
    Weekday,
)
from pizza_radar.core.validator import validate_promo

_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(filename: str) -> list[dict]:
    """Carrega fixture JSON garantindo parsing Decimal nativo."""
    path = os.path.join(_FIXTURES_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return json.loads(f.read(), parse_float=Decimal)


def _observed_at() -> datetime:
    return datetime(2026, 9, 28, 15, 0, 0, tzinfo=timezone.utc)


# ===========================================================================
# 1. Testes de Precisão Monetária
# ===========================================================================

class TestMonetaryPrecision(unittest.TestCase):
    """Testa a conversão de preços sem recurso a float e com tratamento de erros."""

    def test_decimal_799_and_945_to_cents(self) -> None:
        """7.99€ e 9.45€ convertem exatamente para 799 e 945 cêntimos inteiros."""
        self.assertEqual(parse_price_to_cents(Decimal("7.99")), 799)
        self.assertEqual(parse_price_to_cents(Decimal("9.45")), 945)
        self.assertIsInstance(parse_price_to_cents(Decimal("7.99")), int)
        self.assertIsInstance(parse_price_to_cents(Decimal("9.45")), int)

    def test_integer_values_to_cents(self) -> None:
        """Valores inteiros (ex.: 15€, 0€) convertem corretamente."""
        self.assertEqual(parse_price_to_cents(15), 1500)
        self.assertEqual(parse_price_to_cents(0), 0)
        self.assertEqual(parse_price_to_cents(Decimal("15")), 1500)

    def test_string_values_to_cents(self) -> None:
        """Valores em string com ponto ou vírgula convertem para cêntimos."""
        self.assertEqual(parse_price_to_cents("7.99"), 799)
        self.assertEqual(parse_price_to_cents("9.45"), 945)
        self.assertEqual(parse_price_to_cents("7,99"), 799)
        self.assertEqual(parse_price_to_cents("9,45"), 945)
        self.assertEqual(parse_price_to_cents(" 15.00 "), 1500)

    def test_rounding_cases(self) -> None:
        """Casos de arredondamento determinístico (ROUND_HALF_UP)."""
        self.assertEqual(parse_price_to_cents(Decimal("7.994")), 799)
        self.assertEqual(parse_price_to_cents(Decimal("7.995")), 800)
        self.assertEqual(parse_price_to_cents(Decimal("7.996")), 800)
        self.assertEqual(parse_price_to_cents(Decimal("0.005")), 1)
        self.assertEqual(parse_price_to_cents(Decimal("0.004")), 0)

    def test_none_value_returns_none(self) -> None:
        """Valor None devolve None sem erro."""
        self.assertIsNone(parse_price_to_cents(None))

    def test_invalid_string_raises_parse_error(self) -> None:
        """Strings não numéricas ou vazias emitem ParseError explicitamente."""
        with self.assertRaises(ParseError):
            parse_price_to_cents("abc", "price", 101)
        with self.assertRaises(ParseError):
            parse_price_to_cents("", "price", 101)
        with self.assertRaises(ParseError):
            parse_price_to_cents("   ", "price", 101)

    def test_boolean_raises_parse_error(self) -> None:
        """Booleanos emitem ParseError explicitamente."""
        with self.assertRaises(ParseError):
            parse_price_to_cents(True, "price", 101)
        with self.assertRaises(ParseError):
            parse_price_to_cents(False, "price", 101)

    def test_invalid_types_raise_parse_error(self) -> None:
        """Tipos estruturados (list, dict, object) emitem ParseError."""
        with self.assertRaises(ParseError):
            parse_price_to_cents([], "price", 101)
        with self.assertRaises(ParseError):
            parse_price_to_cents({}, "price", 101)
        with self.assertRaises(ParseError):
            parse_price_to_cents(object(), "price", 101)

    def test_non_finite_decimals_raise_parse_error(self) -> None:
        """Valores não-finitos (NaN, Infinity) emitem ParseError."""
        with self.assertRaises(ParseError):
            parse_price_to_cents(Decimal("NaN"), "price", 101)
        with self.assertRaises(ParseError):
            parse_price_to_cents(Decimal("Infinity"), "price", 101)

    def test_negative_values_raise_parse_error(self) -> None:
        """Valores negativos emitem ParseError."""
        with self.assertRaises(ParseError):
            parse_price_to_cents(Decimal("-1.00"), "price", 101)
        with self.assertRaises(ParseError):
            parse_price_to_cents("-5.50", "price", 101)


# ===========================================================================
# 2. Testes de Duplicação e Agregação entre Lojas
# ===========================================================================

class TestStoreDeduplicationAndAggregation(unittest.TestCase):
    """Testa a agregação de lojas e separação determinística de variantes."""

    def setUp(self) -> None:
        self.adapter = PapaJohnsAdapter()
        self.observed_at = _observed_at()

    def test_identical_offer_in_three_stores_produces_single_result(self) -> None:
        """Mesma oferta idêntica em três lojas -> um único UnifiedPromo com 3 lojas."""
        raw_offer = [
            {
                "id": 223,
                "name": "Duo Bestial",
                "description": "2 Pizzas Médias",
                "price": Decimal("17.98"),
                "original_price": None,
                "dispatch_method": "in_store",
                "hidden": False,
            }
        ]

        def mock_fetch(store_id: str, dispatch_method: str, timeout: float = 15.0) -> list[dict]:
            if dispatch_method == "in_store":
                return raw_offer
            return []

        with patch.object(self.adapter, "fetch_raw", side_effect=mock_fetch):
            promos = self.adapter.fetch_promotions()

        # Deve produzir exatamente 1 promoção consolidada
        self.assertEqual(len(promos), 1)
        promo = promos[0]
        # ID determinístico sem store_id embutido
        self.assertEqual(promo.id, "pj_223_in_store")
        # store_ids contém todas as 3 lojas de Lisboa ordenadas
        self.assertEqual(promo.store_ids, ["2", "3", "13"])
        # store_names contém os nomes correspondentes
        self.assertEqual(promo.store_names, ["Amoreiras", "Benfica", "Areeiro"])
        self.assertEqual(promo.store_scope, StoreScope.SPECIFIC_STORES)
        self.assertEqual(promo.price_cents, 1798)

    def test_different_price_in_one_store_produces_separate_variants(self) -> None:
        """Mesma oferta com preço diferente numa loja -> variantes separadas."""
        def mock_fetch(store_id: str, dispatch_method: str, timeout: float = 15.0) -> list[dict]:
            if dispatch_method != "in_store":
                return []
            price = Decimal("19.98") if store_id == "3" else Decimal("17.98")
            return [
                {
                    "id": 223,
                    "name": "Duo Bestial",
                    "description": "2 Pizzas Médias",
                    "price": price,
                    "original_price": None,
                    "dispatch_method": "in_store",
                    "hidden": False,
                }
            ]

        with patch.object(self.adapter, "fetch_raw", side_effect=mock_fetch):
            promos = self.adapter.fetch_promotions()

        # Deve produzir 2 variantes separadas
        self.assertEqual(len(promos), 2)

        # Variante A (lojas 2 e 13 a 17,98€)
        var_a = next((p for p in promos if p.price_cents == 1798), None)
        self.assertIsNotNone(var_a)
        self.assertEqual(var_a.store_ids, ["2", "13"])
        self.assertEqual(var_a.id, "pj_223_in_store_2_13")

        # Variante B (loja 3 a 19,98€)
        var_b = next((p for p in promos if p.price_cents == 1998), None)
        self.assertIsNotNone(var_b)
        self.assertEqual(var_b.store_ids, ["3"])
        self.assertEqual(var_b.id, "pj_223_in_store_3")

    def test_delivery_and_takeaway_produce_separate_results(self) -> None:
        """Delivery e takeaway produzem sempre resultados separados."""
        def mock_fetch(store_id: str, dispatch_method: str, timeout: float = 15.0) -> list[dict]:
            price = Decimal("20.98") if dispatch_method == "pj_delivery" else Decimal("17.98")
            return [
                {
                    "id": 223,
                    "name": "Duo Bestial",
                    "description": "2 Pizzas Médias",
                    "price": price,
                    "original_price": None,
                    "dispatch_method": dispatch_method,
                    "hidden": False,
                }
            ]

        with patch.object(self.adapter, "fetch_raw", side_effect=mock_fetch):
            promos = self.adapter.fetch_promotions()

        # 2 resultados: 1 in_store + 1 delivery (cada um consolidado nas 3 lojas)
        self.assertEqual(len(promos), 2)

        takeaway = next((p for p in promos if DispatchMethod.TAKE_AWAY in p.dispatch_methods), None)
        delivery = next((p for p in promos if DispatchMethod.DELIVERY in p.dispatch_methods), None)

        self.assertIsNotNone(takeaway)
        self.assertIsNotNone(delivery)
        self.assertEqual(takeaway.id, "pj_223_in_store")
        self.assertEqual(delivery.id, "pj_223_pj_delivery")
        self.assertEqual(takeaway.price_cents, 1798)
        self.assertEqual(delivery.price_cents, 2098)
        self.assertEqual(takeaway.store_ids, ["2", "3", "13"])
        self.assertEqual(delivery.store_ids, ["2", "3", "13"])


# ===========================================================================
# 3. Testes de Ofertas Ocultas e Payload Inválido
# ===========================================================================

class TestHiddenOffersAndPayloadValidation(unittest.TestCase):
    """Testa exclusão de hidden=true e deteção estrita de erros em campos obrigatórios."""

    def setUp(self) -> None:
        self.adapter = PapaJohnsAdapter()

    def test_hidden_true_items_are_not_parsed_or_published(self) -> None:
        """Itens com hidden=true são completamente descartados pelo parser."""
        raw = [
            {"id": 1, "name": "Visível", "price": Decimal("10.00"), "hidden": False},
            {"id": 2, "name": "Oculto", "price": Decimal("10.00"), "hidden": True},
            {"id": 3, "name": "Default Sem Hidden", "price": Decimal("10.00")},
        ]
        parsed = self.adapter.parse(raw, "2", "in_store")
        parsed_ids = [p["id"] for p in parsed]

        self.assertIn("1", parsed_ids)
        self.assertNotIn("2", parsed_ids)
        self.assertIn("3", parsed_ids)
        self.assertEqual(len(parsed), 2)

    def test_non_boolean_hidden_raises_parse_error(self) -> None:
        """Campo hidden não-booleano emite ParseError explicitamente."""
        raw = [{"id": 1, "name": "Teste", "price": Decimal("10.00"), "hidden": "not-bool"}]
        with self.assertRaises(ParseError):
            self.adapter.parse(raw, "2", "in_store")

    def test_missing_or_blank_id_raises_parse_error(self) -> None:
        """Campo id em falta, None ou string vazia emite ParseError."""
        with self.assertRaises(ParseError):
            self.adapter.parse([{"name": "Sem ID", "price": Decimal("10.00")}], "2", "in_store")
        with self.assertRaises(ParseError):
            self.adapter.parse([{"id": None, "name": "ID Nulo", "price": Decimal("10.00")}], "2", "in_store")
        with self.assertRaises(ParseError):
            self.adapter.parse([{"id": "   ", "name": "ID Vazio", "price": Decimal("10.00")}], "2", "in_store")

    def test_missing_or_blank_name_raises_parse_error(self) -> None:
        """Campo name em falta, None ou vazio emite ParseError."""
        with self.assertRaises(ParseError):
            self.adapter.parse([{"id": 1, "price": Decimal("10.00")}], "2", "in_store")
        with self.assertRaises(ParseError):
            self.adapter.parse([{"id": 1, "name": "", "price": Decimal("10.00")}], "2", "in_store")
        with self.assertRaises(ParseError):
            self.adapter.parse([{"id": 1, "name": "   ", "price": Decimal("10.00")}], "2", "in_store")

    def test_invalid_price_raises_parse_error_explicitly(self) -> None:
        """Preço inválido no payload não vira None silenciosamente: emite ParseError."""
        raw = [{"id": 1, "name": "Inválido", "price": "preço-inválido"}]
        with self.assertRaises(ParseError):
            self.adapter.parse(raw, "2", "in_store")

    def test_invalid_original_price_raises_parse_error_explicitly(self) -> None:
        """original_price inválido no payload emite ParseError."""
        raw = [{"id": 1, "name": "Promo", "price": Decimal("10.00"), "original_price": "lixo"}]
        with self.assertRaises(ParseError):
            self.adapter.parse(raw, "2", "in_store")

    def test_invalid_pictures_type_raises_parse_error(self) -> None:
        """pictures com tipo que não seja list emite ParseError."""
        raw = [{"id": 1, "name": "Promo", "price": Decimal("10.00"), "pictures": "não-é-lista"}]
        with self.assertRaises(ParseError):
            self.adapter.parse(raw, "2", "in_store")

    def test_invalid_availability_type_raises_parse_error(self) -> None:
        """availability com tipo inválido emite ParseError."""
        raw = [{"id": 1, "name": "Promo", "price": Decimal("10.00"), "availability": 12345}]
        with self.assertRaises(ParseError):
            self.adapter.parse(raw, "2", "in_store")

    def test_composition_is_never_invented_when_unproven(self) -> None:
        """pizza_count é None, pizza_size=UNKNOWN quando a descrição não comprova quantidade/tamanho."""
        raw_item = {
            "id": "223",
            "name": "Super Promoção",
            "description": "Oferta especial da semana sem menção a quantidade",
            "price_cents": 1798,
            "original_price_cents": None,
            "request_dispatch_method": "in_store",
            "item_dispatch_method": "in_store",
            "store_id": "2",
            "availability": [],
            "start_datetime": None,
            "end_datetime": None,
            "pictures": [],
            "conditions": "",
        }
        promo = self.adapter.adapt(raw_item, _observed_at())
        self.assertIsNone(promo.pizza_count)
        self.assertEqual(promo.pizza_size, PizzaSize.UNKNOWN)
        self.assertFalse(promo.is_comparable_for_unit_price)

    def test_composition_extraction_from_explicit_patterns(self) -> None:
        """Extrai pizza_count e pizza_size apenas de padrões explícitos como '2 Médias'."""
        raw_item = {
            "id": "224",
            "name": "Duo Bestial",
            "description": "2 Médias desde 8,99€ cada",
            "price_cents": 1798,
            "original_price_cents": None,
            "request_dispatch_method": "in_store",
            "item_dispatch_method": "in_store",
            "store_id": "2",
            "availability": [],
            "start_datetime": None,
            "end_datetime": None,
            "pictures": [],
            "conditions": "",
        }
        promo = self.adapter.adapt(raw_item, _observed_at())
        self.assertEqual(promo.pizza_count, 2)
        self.assertEqual(promo.pizza_size, PizzaSize.MEDIUM)
        self.assertTrue(promo.is_comparable_for_unit_price)
        self.assertEqual(promo.price_per_pizza_cents, 899)


# ===========================================================================
# 4. Testes do Parser com Fixtures Sanitizadas
# ===========================================================================

class TestPapaJohnsAdapterParse(unittest.TestCase):
    """Testa parse() com fixtures sanitizadas carregadas via parse_float=Decimal."""

    def setUp(self) -> None:
        self.adapter = PapaJohnsAdapter()
        self.in_store_raw = _load_fixture("papa_johns_in_store.json")
        self.delivery_raw = _load_fixture("papa_johns_pj_delivery.json")

    def test_parse_in_store_filters_hidden_items(self) -> None:
        """Item 252 (hidden=true) não aparece no resultado de parse()."""
        parsed = self.adapter.parse(self.in_store_raw, "2", "in_store")
        parsed_ids = [p["id"] for p in parsed]
        # Na fixture, item 252 tem hidden=true
        self.assertNotIn("252", parsed_ids)
        # Itens não-ocultos estão presentes
        self.assertIn("207", parsed_ids)
        self.assertIn("222", parsed_ids)
        self.assertIn("218", parsed_ids)

    def test_parse_prices_are_integer_cents(self) -> None:
        """Preços parseados já se encontram em cêntimos inteiros (sem float)."""
        parsed = self.adapter.parse(self.in_store_raw, "2", "in_store")
        for item in parsed:
            if item["price_cents"] is not None:
                self.assertIsInstance(item["price_cents"], int)
                self.assertNotIsInstance(item["price_cents"], bool)

    def test_parse_channel_context_delivery(self) -> None:
        """Itens 'both' usam description_delivery quando solicitado pj_delivery."""
        parsed = self.adapter.parse(self.delivery_raw, "2", "pj_delivery")
        papito = next((p for p in parsed if p["id"] == "222"), None)
        self.assertIsNotNone(papito)
        self.assertIn("10,99€", papito["description"])

    def test_parse_anomaly_218_original_price_discarded(self) -> None:
        """Item 218: original_price (16.64) < price (16.99) resulta em original_price_cents=None."""
        parsed = self.adapter.parse(self.in_store_raw, "2", "in_store")
        item_218 = next((p for p in parsed if p["id"] == "218"), None)
        self.assertIsNotNone(item_218)
        self.assertEqual(item_218["price_cents"], 1699)
        self.assertIsNone(item_218["original_price_cents"])


# ===========================================================================
# 5. Testes da Camada Adapt
# ===========================================================================

class TestPapaJohnsAdapterAdapt(unittest.TestCase):
    """Testa adapt() e a conformidade com o contrato canónico UnifiedPromo."""

    def setUp(self) -> None:
        self.adapter = PapaJohnsAdapter()
        self.observed_at = _observed_at()

    def _base_parsed(self) -> dict:
        return {
            "id": "207",
            "name": "A MAIS FRESCA",
            "description": "Pizza média fina por 7.99€",
            "price_cents": 799,
            "original_price_cents": 945,
            "request_dispatch_method": "in_store",
            "item_dispatch_method": "in_store",
            "store_id": "2",
            "availability": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
            "start_datetime": "2024-02-05T00:00:00.000Z",
            "end_datetime": "2028-12-31T00:00:00.000Z",
            "pictures": [
                {"url": "https://cdn.papajohns.pt/fresca_photo.webp", "category": "photo"},
            ],
            "conditions": "",
        }

    def test_adapt_produces_valid_unified_promo(self) -> None:
        """UnifiedPromo produzido passa na validação estrita do contrato."""
        promo = self.adapter.adapt(self._base_parsed(), self.observed_at)
        validated = validate_promo(promo)
        self.assertEqual(validated.vendor, Brand.PAPA_JOHNS)
        self.assertEqual(validated.price_cents, 799)
        self.assertEqual(validated.original_price_cents, 945)
        self.assertEqual(validated.price_euros, 7.99)
        self.assertEqual(validated.original_price_euros, 9.45)
        self.assertEqual(validated.savings_amount_cents, 146)

    def test_adapt_store_aggregation(self) -> None:
        """store_ids e store_names agregam múltiplas lojas corretamente."""
        promo = self.adapter.adapt(
            self._base_parsed(),
            self.observed_at,
            store_ids=["2", "13", "3"],
            variant_id="pj_207_in_store",
        )
        self.assertEqual(promo.id, "pj_207_in_store")
        self.assertEqual(promo.store_ids, ["2", "3", "13"])
        self.assertEqual(promo.store_names, ["Amoreiras", "Benfica", "Areeiro"])

    def test_adapt_rejects_naive_datetime(self) -> None:
        """Data naive levanta ValueError."""
        naive = datetime(2026, 9, 28, 15, 0, 0)
        with self.assertRaises(ValueError):
            self.adapter.adapt(self._base_parsed(), naive)


# ===========================================================================
# 6. Testes de Erros e Integração
# ===========================================================================

class TestPapaJohnsAdapterErrorsAndIntegration(unittest.TestCase):
    """Testa propagação de exceções e execução ponta-a-ponta."""

    def setUp(self) -> None:
        self.adapter = PapaJohnsAdapter()

    def test_network_error_propagates(self) -> None:
        """NetworkError propaga com vendor=PAPA_JOHNS."""
        with patch.object(self.adapter, "fetch_raw", side_effect=NetworkError("Timeout", vendor=Brand.PAPA_JOHNS)):
            with self.assertRaises(NetworkError) as ctx:
                self.adapter.fetch_promotions()
            self.assertEqual(ctx.exception.vendor, Brand.PAPA_JOHNS)

    def test_parse_error_propagates(self) -> None:
        """ParseError propaga com vendor=PAPA_JOHNS."""
        with patch.object(self.adapter, "fetch_raw", side_effect=ParseError("Malformed", vendor=Brand.PAPA_JOHNS)):
            with self.assertRaises(ParseError) as ctx:
                self.adapter.fetch_promotions()
            self.assertEqual(ctx.exception.vendor, Brand.PAPA_JOHNS)

    def test_fetch_promotions_full_mock_integration(self) -> None:
        """Execução completa com dados sanitizados passa em todas as asserções."""
        in_store = _load_fixture("papa_johns_in_store.json")
        delivery = _load_fixture("papa_johns_pj_delivery.json")

        def mock_fetch(store_id: str, dispatch_method: str, timeout: float = 15.0) -> list[dict]:
            if dispatch_method == "in_store":
                return in_store
            return delivery

        with patch.object(self.adapter, "fetch_raw", side_effect=mock_fetch):
            promos = self.adapter.fetch_promotions()

        self.assertGreater(len(promos), 0)
        # Todos passam na validação do contrato
        for p in promos:
            validate_promo(p)
            self.assertEqual(p.vendor, Brand.PAPA_JOHNS)
            self.assertEqual(p.location_scope, "Lisboa")
            # Todas as promoções agregaram as 3 lojas de Lisboa (pois as fixtures são idênticas)
            self.assertEqual(p.store_ids, ["2", "3", "13"])
            self.assertEqual(p.store_names, ["Amoreiras", "Benfica", "Areeiro"])

        # Nenhum item oculto (hidden=true) foi publicado
        promo_ids = [p.id for p in promos]
        self.assertFalse(any("252_in_store" in pid for pid in promo_ids))


if __name__ == "__main__":
    unittest.main()
