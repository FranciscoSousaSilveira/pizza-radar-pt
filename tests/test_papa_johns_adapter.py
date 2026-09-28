"""Testes unitários para PapaJohnsAdapter.

Estrutura de testes (sem dependência de rede — 100% determinísticos):
  - TestPapaJohnsAdapterHelpers: testa funções auxiliares independentes.
  - TestPapaJohnsAdapterParse: testa parse() com fixtures sanitizadas.
  - TestPapaJohnsAdapterAdapt: testa adapt() com dicionários construídos diretamente.
  - TestPapaJohnsAdapterErrors: testa propagação de NetworkError e ParseError.
  - TestPapaJohnsAdapterIntegration: testa fetch_promotions() com fetch_raw() substituído.

Fixtures sanitizadas em tests/fixtures/papa_johns_in_store.json e
tests/fixtures/papa_johns_pj_delivery.json — estrutura validada empiricamente
pelo source-researcher em 2026-09-28 (confirmada contra a API real).

Nota do adaptador: pizza_count é sempre None porque o endpoint
/v1/offers/promotions não expõe offer_groups; incluída anomalia ID 218
onde original_price < price.
"""

from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from pizza_radar.adapters.papa_johns import (
    LISBON_STORES,
    PapaJohnsAdapter,
    _parse_availability,
    _parse_pizza_size,
    _select_image_url,
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


# ---------------------------------------------------------------------------
# Utilitários de teste
# ---------------------------------------------------------------------------

_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(filename: str) -> list[dict]:
    """Carrega um ficheiro de fixture JSON."""
    path = os.path.join(_FIXTURES_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _observed_at() -> datetime:
    """Momento de observação fixo, timezone-aware, para testes determinísticos."""
    return datetime(2026, 9, 28, 15, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# TestPapaJohnsAdapterHelpers
# ---------------------------------------------------------------------------

class TestPapaJohnsAdapterHelpers(unittest.TestCase):
    """Testa funções auxiliares independentes."""

    def test_parse_pizza_size_known_values(self) -> None:
        """Verifica mapeamento de strings conhecidas."""
        self.assertEqual(_parse_pizza_size("medium"), PizzaSize.MEDIUM)
        self.assertEqual(_parse_pizza_size("individual"), PizzaSize.INDIVIDUAL)
        self.assertEqual(_parse_pizza_size("large"), PizzaSize.LARGE)
        self.assertEqual(_parse_pizza_size("family"), PizzaSize.FAMILY)
        self.assertEqual(_parse_pizza_size("familiar"), PizzaSize.FAMILY)
        self.assertEqual(_parse_pizza_size("MEDIUM"), PizzaSize.MEDIUM)

    def test_parse_pizza_size_unknown(self) -> None:
        """Valores não reconhecidos devolvem UNKNOWN sem lançar exceção."""
        self.assertEqual(_parse_pizza_size(None), PizzaSize.UNKNOWN)
        self.assertEqual(_parse_pizza_size(""), PizzaSize.UNKNOWN)
        self.assertEqual(_parse_pizza_size("jumbo"), PizzaSize.UNKNOWN)

    def test_parse_availability_list(self) -> None:
        """Disponibilidade em formato lista mapeada corretamente."""
        days = _parse_availability(["monday", "tuesday", "friday"])
        self.assertIn(Weekday.MONDAY, days)
        self.assertIn(Weekday.TUESDAY, days)
        self.assertIn(Weekday.FRIDAY, days)
        self.assertEqual(len(days), 3)

    def test_parse_availability_all_days(self) -> None:
        """Disponibilidade todos os dias retorna 7 Weekdays."""
        all_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        days = _parse_availability(all_days)
        self.assertEqual(len(days), 7)

    def test_parse_availability_empty(self) -> None:
        """Lista vazia retorna lista vazia."""
        days = _parse_availability([])
        self.assertEqual(days, [])

    def test_parse_availability_none(self) -> None:
        """None retorna lista vazia."""
        days = _parse_availability(None)
        self.assertEqual(days, [])

    def test_parse_availability_no_duplicates(self) -> None:
        """Dias duplicados não geram duplicados no resultado."""
        days = _parse_availability(["monday", "monday", "tuesday"])
        self.assertEqual(len(days), 2)

    def test_select_image_url_prefers_photo_for_in_store(self) -> None:
        """Para in_store, prefere 'photo' em vez de 'delivery_photo'."""
        pictures = [
            {"url": "https://cdn.example.com/delivery.webp", "category": "delivery_photo"},
            {"url": "https://cdn.example.com/photo.webp", "category": "photo"},
        ]
        url = _select_image_url(pictures, "in_store")
        self.assertEqual(url, "https://cdn.example.com/photo.webp")

    def test_select_image_url_prefers_delivery_photo_for_pj_delivery(self) -> None:
        """Para pj_delivery, prefere 'delivery_photo' em vez de 'photo'."""
        pictures = [
            {"url": "https://cdn.example.com/delivery.webp", "category": "delivery_photo"},
            {"url": "https://cdn.example.com/photo.webp", "category": "photo"},
        ]
        url = _select_image_url(pictures, "pj_delivery")
        self.assertEqual(url, "https://cdn.example.com/delivery.webp")

    def test_select_image_url_fallback(self) -> None:
        """Se a categoria preferida não existe, usa qualquer URL disponível."""
        pictures = [
            {"url": "https://cdn.example.com/photo_app.webp", "category": "photo_app"},
        ]
        url = _select_image_url(pictures, "in_store")
        self.assertIsNotNone(url)

    def test_select_image_url_none_on_empty(self) -> None:
        """Lista vazia retorna None."""
        self.assertIsNone(_select_image_url([], "in_store"))
        self.assertIsNone(_select_image_url(None, "in_store"))

    def test_lisbon_stores_constant(self) -> None:
        """Confirma as 3 lojas de Lisboa documentadas."""
        self.assertIn("2", LISBON_STORES)   # Amoreiras
        self.assertIn("13", LISBON_STORES)  # Areeiro
        self.assertIn("3", LISBON_STORES)   # Benfica
        self.assertEqual(len(LISBON_STORES), 3)


# ---------------------------------------------------------------------------
# TestPapaJohnsAdapterParse
# ---------------------------------------------------------------------------

class TestPapaJohnsAdapterParse(unittest.TestCase):
    """Testa parse() com fixtures sanitizadas — sem acesso à rede."""

    def setUp(self) -> None:
        self.adapter = PapaJohnsAdapter()
        self.in_store_raw = _load_fixture("papa_johns_in_store.json")
        self.delivery_raw = _load_fixture("papa_johns_pj_delivery.json")

    def test_parse_in_store_returns_correct_count(self) -> None:
        """Confirma que parse() extrai todos os elementos da fixture in_store."""
        parsed = self.adapter.parse(self.in_store_raw, "2", "in_store")
        self.assertEqual(len(parsed), len(self.in_store_raw))

    def test_parse_mandatory_fields_present(self) -> None:
        """Cada elemento parseado tem id, name, description, request_dispatch_method, store_id."""
        parsed = self.adapter.parse(self.in_store_raw, "2", "in_store")
        for item in parsed:
            self.assertIn("id", item)
            self.assertIn("name", item)
            self.assertIn("description", item)
            self.assertIn("request_dispatch_method", item)
            self.assertIn("store_id", item)
            self.assertEqual(item["store_id"], "2")
            self.assertEqual(item["request_dispatch_method"], "in_store")

    def test_parse_delivery_uses_name_delivery_for_both_items(self) -> None:
        """Itens com dispatch_method='both' em pedido delivery usam name_delivery."""
        parsed = self.adapter.parse(self.delivery_raw, "2", "pj_delivery")
        duo = next((p for p in parsed if p["id"] == "252"), None)
        self.assertIsNotNone(duo, "Item 252 não encontrado na fixture delivery")
        # name_delivery = "Duo Bestial + entrada" (igual ao name neste caso)
        self.assertEqual(duo["name"], "Duo Bestial + entrada")

    def test_parse_delivery_uses_description_delivery(self) -> None:
        """Itens 'both' em pedido delivery usam description_delivery."""
        parsed = self.adapter.parse(self.delivery_raw, "2", "pj_delivery")
        papito = next((p for p in parsed if p["id"] == "222"), None)
        self.assertIsNotNone(papito)
        self.assertIn("10,99€", papito["description"])  # description_delivery

    def test_parse_in_store_uses_name_not_name_delivery(self) -> None:
        """Itens 'both' em pedido in_store usam name (não name_delivery)."""
        parsed = self.adapter.parse(self.in_store_raw, "2", "in_store")
        papito = next((p for p in parsed if p["id"] == "222"), None)
        self.assertIsNotNone(papito)
        # description do in_store tem 6,99€ (não 10,99€ do delivery)
        self.assertIn("6,99€", papito["description"])

    def test_parse_prices_are_floats_or_none(self) -> None:
        """Preços extraídos são números ou None — nunca strings."""
        parsed = self.adapter.parse(self.in_store_raw, "2", "in_store")
        for item in parsed:
            price = item.get("price")
            original = item.get("original_price")
            if price is not None:
                self.assertIsInstance(price, (int, float))
            if original is not None:
                self.assertIsInstance(original, (int, float))

    def test_parse_anomaly_id_218_price_higher_than_original(self) -> None:
        """ID 218 na fixture tem price=16.99 > original_price=16.64 (anomalia real)."""
        parsed = self.adapter.parse(self.in_store_raw, "2", "in_store")
        anomaly = next((p for p in parsed if p["id"] == "218"), None)
        self.assertIsNotNone(anomaly)
        self.assertGreater(anomaly["price"], anomaly["original_price"])

    def test_parse_pictures_preserved(self) -> None:
        """Campo pictures é preservado para seleção posterior de image_url."""
        parsed = self.adapter.parse(self.in_store_raw, "2", "in_store")
        fresca = next((p for p in parsed if p["id"] == "207"), None)
        self.assertIsNotNone(fresca)
        self.assertIsNotNone(fresca["pictures"])
        self.assertGreater(len(fresca["pictures"]), 0)

    def test_parse_start_end_datetime_preserved(self) -> None:
        """start_datetime e end_datetime são preservados como strings."""
        parsed = self.adapter.parse(self.in_store_raw, "2", "in_store")
        fresca = next((p for p in parsed if p["id"] == "207"), None)
        self.assertIsNotNone(fresca)
        self.assertEqual(fresca["start_datetime"], "2024-02-05T00:00:00.000Z")
        self.assertEqual(fresca["end_datetime"], "2028-12-31T00:00:00.000Z")

    def test_parse_empty_list_returns_empty(self) -> None:
        """Lista vazia de raw devolve lista vazia sem erro."""
        parsed = self.adapter.parse([], "2", "in_store")
        self.assertEqual(parsed, [])

    def test_parse_missing_id_raises_parse_error(self) -> None:
        """Elemento sem 'id' lança ParseError."""
        bad_raw = [{"name": "Sem ID", "price": 10.0}]
        with self.assertRaises(ParseError):
            self.adapter.parse(bad_raw, "2", "in_store")

    def test_parse_missing_name_raises_parse_error(self) -> None:
        """Elemento sem 'name' lança ParseError."""
        bad_raw = [{"id": 99}]
        with self.assertRaises(ParseError):
            self.adapter.parse(bad_raw, "2", "in_store")

    def test_parse_non_dict_element_raises_parse_error(self) -> None:
        """Elemento que não é dict lança ParseError."""
        bad_raw = ["string_inválida"]
        with self.assertRaises(ParseError):
            self.adapter.parse(bad_raw, "2", "in_store")  # type: ignore[arg-type]

    def test_parse_non_list_raises_parse_error(self) -> None:
        """Payload que não é list lança ParseError."""
        with self.assertRaises(ParseError):
            self.adapter.parse({"key": "value"}, "2", "in_store")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TestPapaJohnsAdapterAdapt
# ---------------------------------------------------------------------------

class TestPapaJohnsAdapterAdapt(unittest.TestCase):
    """Testa adapt() com dicionários construídos diretamente — sem I/O."""

    def setUp(self) -> None:
        self.adapter = PapaJohnsAdapter()
        self.observed_at = _observed_at()

    def _base_item(self) -> dict:
        """Item mínimo válido para adapt() — baseado em ID 207 da fixture."""
        return {
            "id": "207",
            "name": "A MAIS FRESCA",
            "description": "Pizza média com massa fina e estaladiça com 2 ingredientes à escolha por apenas 7.99€",
            "price": 7.99,
            "original_price": 9.45,
            "request_dispatch_method": "in_store",
            "item_dispatch_method": "in_store",
            "store_id": "2",
            "availability": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
            "start_datetime": "2024-02-05T00:00:00.000Z",
            "end_datetime": "2028-12-31T00:00:00.000Z",
            "pictures": [
                {"id": 3999, "url": "https://cdn.papajohns.pt/fresca_delivery.webp", "category": "delivery_photo"},
                {"id": 3998, "url": "https://cdn.papajohns.pt/fresca_photo.webp", "category": "photo"},
            ],
            "position": 2,
            "hidden": False,
            "promoted": False,
            "conditions": "",
        }

    def test_adapt_price_to_integer_cents(self) -> None:
        """Preço float 7.99€ convertido para 799 cêntimos inteiros."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertEqual(promo.price_cents, 799)
        self.assertIsInstance(promo.price_cents, int)
        self.assertNotIsInstance(promo.price_cents, bool)

    def test_adapt_original_price_to_integer_cents(self) -> None:
        """original_price 9.45€ convertido para 945 cêntimos inteiros."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertEqual(promo.original_price_cents, 945)

    def test_adapt_price_euros_property(self) -> None:
        """Propriedade price_euros devolve o valor correto em euros."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertAlmostEqual(promo.price_euros, 7.99, places=2)

    def test_adapt_vendor_is_papa_johns(self) -> None:
        """Vendedor é sempre PAPA_JOHNS."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertEqual(promo.vendor, Brand.PAPA_JOHNS)

    def test_adapt_id_is_canonical(self) -> None:
        """ID canónico inclui prefixo pj_, id da oferta, loja e modalidade do pedido."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertEqual(promo.id, "pj_207_2_in_store")

    def test_adapt_dispatch_method_in_store(self) -> None:
        """in_store mapeado para TAKE_AWAY."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertEqual(promo.dispatch_methods, [DispatchMethod.TAKE_AWAY])

    def test_adapt_dispatch_method_pj_delivery(self) -> None:
        """pj_delivery mapeado para DELIVERY."""
        item = self._base_item()
        item["request_dispatch_method"] = "pj_delivery"
        item["item_dispatch_method"] = "pj_delivery"
        promo = self.adapter.adapt(item, self.observed_at)
        self.assertEqual(promo.dispatch_methods, [DispatchMethod.DELIVERY])

    def test_adapt_store_scope_specific_stores(self) -> None:
        """store_scope é sempre SPECIFIC_STORES com IDs e nomes de loja."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertEqual(promo.store_scope, StoreScope.SPECIFIC_STORES)
        self.assertIn("2", promo.store_ids)
        self.assertIn("Amoreiras", promo.store_names)

    def test_adapt_location_scope_is_lisboa(self) -> None:
        """location_scope é sempre 'Lisboa'."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertEqual(promo.location_scope, "Lisboa")

    def test_adapt_observed_at_is_timezone_aware(self) -> None:
        """observed_at preserva timezone-awareness do datetime de entrada."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertIn("+", promo.observed_at)

    def test_adapt_pizza_count_is_always_none(self) -> None:
        """pizza_count é sempre None — não disponível neste endpoint."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertIsNone(promo.pizza_count)

    def test_adapt_pizza_size_is_always_unknown(self) -> None:
        """pizza_size é sempre UNKNOWN — não disponível neste endpoint."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertEqual(promo.pizza_size, PizzaSize.UNKNOWN)

    def test_adapt_included_items_is_always_empty(self) -> None:
        """included_items é sempre [] — offer_groups não existe neste endpoint."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertEqual(promo.included_items, [])

    def test_adapt_is_not_comparable_for_unit_price(self) -> None:
        """is_comparable_for_unit_price=False porque pizza_count é None."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertFalse(promo.is_comparable_for_unit_price)
        self.assertIsNone(promo.price_per_pizza_cents)

    def test_adapt_image_url_prefers_photo_for_in_store(self) -> None:
        """in_store: image_url seleciona 'photo' em vez de 'delivery_photo'."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertEqual(promo.image_url, "https://cdn.papajohns.pt/fresca_photo.webp")

    def test_adapt_image_url_prefers_delivery_photo_for_delivery(self) -> None:
        """pj_delivery: image_url seleciona 'delivery_photo'."""
        item = self._base_item()
        item["request_dispatch_method"] = "pj_delivery"
        promo = self.adapter.adapt(item, self.observed_at)
        self.assertEqual(promo.image_url, "https://cdn.papajohns.pt/fresca_delivery.webp")

    def test_adapt_image_url_none_when_pictures_empty(self) -> None:
        """image_url é None quando pictures está vazio."""
        item = self._base_item()
        item["pictures"] = []
        promo = self.adapter.adapt(item, self.observed_at)
        self.assertIsNone(promo.image_url)

    def test_adapt_image_url_none_when_pictures_none(self) -> None:
        """image_url é None quando pictures é None."""
        item = self._base_item()
        item["pictures"] = None
        promo = self.adapter.adapt(item, self.observed_at)
        self.assertIsNone(promo.image_url)

    def test_adapt_valid_from_and_until_from_api_dates(self) -> None:
        """valid_from e valid_until preenchidos a partir de start/end_datetime da API."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertEqual(promo.valid_from, "2024-02-05T00:00:00.000Z")
        self.assertEqual(promo.valid_until, "2028-12-31T00:00:00.000Z")

    def test_adapt_valid_from_until_none_when_absent(self) -> None:
        """valid_from e valid_until são None quando start/end_datetime é None."""
        item = self._base_item()
        item["start_datetime"] = None
        item["end_datetime"] = None
        promo = self.adapter.adapt(item, self.observed_at)
        self.assertIsNone(promo.valid_from)
        self.assertIsNone(promo.valid_until)

    def test_adapt_days_of_week_all_days(self) -> None:
        """Promoção disponível todos os dias tem 7 Weekdays."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertEqual(len(promo.days_of_week), 7)

    def test_adapt_rejects_naive_observed_at(self) -> None:
        """observed_at sem timezone levanta ValueError."""
        naive_dt = datetime(2026, 9, 28, 15, 0, 0)
        with self.assertRaises(ValueError):
            self.adapter.adapt(self._base_item(), naive_dt)

    def test_adapt_anomaly_original_price_lower_than_price_ignored(self) -> None:
        """ID 218: original_price (16.64) < price (16.99) → original_price_cents=None."""
        item = self._base_item()
        item["id"] = "218"
        item["price"] = 16.99
        item["original_price"] = 16.64
        promo = self.adapter.adapt(item, self.observed_at)
        self.assertEqual(promo.price_cents, 1699)
        self.assertIsNone(promo.original_price_cents)  # Ignorado por inconsistência

    def test_adapt_output_passes_validate_promo(self) -> None:
        """Saída de adapt() passa na validação do contrato canónico."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        validated = validate_promo(promo)
        self.assertEqual(validated.id, "pj_207_2_in_store")

    def test_adapt_savings_amount_when_valid_original(self) -> None:
        """savings_amount_cents calculado corretamente quando original > price."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        # 945 - 799 = 146 cêntimos
        self.assertEqual(promo.savings_amount_cents, 146)

    def test_adapt_source_url_is_valid(self) -> None:
        """source_url é sempre o URL de promoções da Papa John's."""
        promo = self.adapter.adapt(self._base_item(), self.observed_at)
        self.assertTrue(promo.source_url.startswith("https://"))
        self.assertIn("papajohns.pt", promo.source_url)


# ---------------------------------------------------------------------------
# TestPapaJohnsAdapterErrors
# ---------------------------------------------------------------------------

class TestPapaJohnsAdapterErrors(unittest.TestCase):
    """Testa propagação de NetworkError e ParseError."""

    def setUp(self) -> None:
        self.adapter = PapaJohnsAdapter()

    def test_fetch_promotions_propagates_network_error(self) -> None:
        """NetworkError numa loja propaga sem ser suprimida."""
        with patch.object(
            self.adapter,
            "fetch_raw",
            side_effect=NetworkError("Timeout", vendor=Brand.PAPA_JOHNS),
        ):
            with self.assertRaises(NetworkError) as ctx:
                self.adapter.fetch_promotions()
            self.assertEqual(ctx.exception.vendor, Brand.PAPA_JOHNS)

    def test_fetch_promotions_propagates_parse_error(self) -> None:
        """ParseError numa loja propaga sem ser suprimida."""
        with patch.object(
            self.adapter,
            "fetch_raw",
            side_effect=ParseError("JSON malformado", vendor=Brand.PAPA_JOHNS),
        ):
            with self.assertRaises(ParseError) as ctx:
                self.adapter.fetch_promotions()
            self.assertEqual(ctx.exception.vendor, Brand.PAPA_JOHNS)

    def test_parse_propagates_parse_error_on_bad_structure(self) -> None:
        """parse() com estrutura inesperada lança ParseError com vendor correto."""
        bad_payload = [{"no_id": True, "no_name": True}]
        with self.assertRaises(ParseError) as ctx:
            self.adapter.parse(bad_payload, "2", "in_store")
        self.assertEqual(ctx.exception.vendor, Brand.PAPA_JOHNS)

    def test_parse_error_vendor_is_papa_johns(self) -> None:
        """ParseError de payload não-lista tem vendor=PAPA_JOHNS."""
        with self.assertRaises(ParseError) as ctx:
            self.adapter.parse({"unexpected": "dict"}, "2", "in_store")  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.vendor, Brand.PAPA_JOHNS)


# ---------------------------------------------------------------------------
# TestPapaJohnsAdapterIntegration
# ---------------------------------------------------------------------------

class TestPapaJohnsAdapterIntegration(unittest.TestCase):
    """Testa fetch_promotions() com fetch_raw() substituído por fixtures — sem rede."""

    def setUp(self) -> None:
        self.adapter = PapaJohnsAdapter()
        self.in_store_raw = _load_fixture("papa_johns_in_store.json")
        self.delivery_raw = _load_fixture("papa_johns_pj_delivery.json")

    def _mock_fetch_raw(self, store_id: str, dispatch_method: str, timeout: float = 15.0) -> list[dict]:
        """Substitui fetch_raw com dados de fixtures por dispatch_method."""
        if dispatch_method == "in_store":
            return self.in_store_raw
        return self.delivery_raw

    def test_fetch_promotions_returns_unified_promos(self) -> None:
        """fetch_promotions() com mock devolve lista de UnifiedPromo."""
        with patch.object(self.adapter, "fetch_raw", side_effect=self._mock_fetch_raw):
            promos = self.adapter.fetch_promotions()
        self.assertIsInstance(promos, list)
        self.assertGreater(len(promos), 0)
        for promo in promos:
            self.assertIsInstance(promo, UnifiedPromo)

    def test_fetch_promotions_all_promos_pass_validation(self) -> None:
        """Todos os UnifiedPromo devolvidos passam na validação do contrato."""
        with patch.object(self.adapter, "fetch_raw", side_effect=self._mock_fetch_raw):
            promos = self.adapter.fetch_promotions()
        for promo in promos:
            validate_promo(promo)  # não lança exceção = OK

    def test_fetch_promotions_vendor_is_papa_johns(self) -> None:
        """Todos os registos têm vendor=PAPA_JOHNS."""
        with patch.object(self.adapter, "fetch_raw", side_effect=self._mock_fetch_raw):
            promos = self.adapter.fetch_promotions()
        for promo in promos:
            self.assertEqual(promo.vendor, Brand.PAPA_JOHNS)

    def test_fetch_promotions_no_duplicate_ids(self) -> None:
        """Nenhum ID duplicado na lista final."""
        with patch.object(self.adapter, "fetch_raw", side_effect=self._mock_fetch_raw):
            promos = self.adapter.fetch_promotions()
        ids = [p.id for p in promos]
        self.assertEqual(len(ids), len(set(ids)), "IDs duplicados encontrados")

    def test_fetch_promotions_location_scope_is_lisboa(self) -> None:
        """Todos os registos têm location_scope='Lisboa'."""
        with patch.object(self.adapter, "fetch_raw", side_effect=self._mock_fetch_raw):
            promos = self.adapter.fetch_promotions()
        for promo in promos:
            self.assertEqual(promo.location_scope, "Lisboa")

    def test_fetch_promotions_price_cents_are_integers(self) -> None:
        """Todos os price_cents não-None são inteiros (não float)."""
        with patch.object(self.adapter, "fetch_raw", side_effect=self._mock_fetch_raw):
            promos = self.adapter.fetch_promotions()
        for promo in promos:
            if promo.price_cents is not None:
                self.assertIsInstance(promo.price_cents, int)
                self.assertNotIsInstance(promo.price_cents, bool)

    def test_fetch_promotions_store_scope_specific_stores(self) -> None:
        """Todos os registos têm store_scope=SPECIFIC_STORES."""
        with patch.object(self.adapter, "fetch_raw", side_effect=self._mock_fetch_raw):
            promos = self.adapter.fetch_promotions()
        for promo in promos:
            self.assertEqual(promo.store_scope, StoreScope.SPECIFIC_STORES)
            self.assertGreater(len(promo.store_ids), 0)

    def test_fetch_promotions_observed_at_timezone_aware(self) -> None:
        """observed_at de todos os registos tem offset UTC explícito."""
        with patch.object(self.adapter, "fetch_raw", side_effect=self._mock_fetch_raw):
            promos = self.adapter.fetch_promotions()
        for promo in promos:
            self.assertTrue(
                "+" in promo.observed_at or "Z" in promo.observed_at,
                f"observed_at sem timezone: {promo.observed_at}",
            )

    def test_fetch_promotions_contains_in_store_and_delivery(self) -> None:
        """Resultado contém promoções tanto de TAKE_AWAY como de DELIVERY."""
        with patch.object(self.adapter, "fetch_raw", side_effect=self._mock_fetch_raw):
            promos = self.adapter.fetch_promotions()
        dispatch_methods = {m for p in promos for m in p.dispatch_methods}
        self.assertIn(DispatchMethod.TAKE_AWAY, dispatch_methods)
        self.assertIn(DispatchMethod.DELIVERY, dispatch_methods)

    def test_fetch_promotions_pizza_count_always_none(self) -> None:
        """pizza_count é None em todos os registos (não disponível neste endpoint)."""
        with patch.object(self.adapter, "fetch_raw", side_effect=self._mock_fetch_raw):
            promos = self.adapter.fetch_promotions()
        for promo in promos:
            self.assertIsNone(promo.pizza_count)

    def test_fetch_promotions_anomaly_218_has_no_original_price(self) -> None:
        """ID 218 (anomalia: original < price) não tem original_price_cents."""
        with patch.object(self.adapter, "fetch_raw", side_effect=self._mock_fetch_raw):
            promos = self.adapter.fetch_promotions()
        # Procura qualquer promo derivada do ID 218 (em qualquer loja/modalidade)
        anomaly_promos = [p for p in promos if "_218_" in p.id]
        self.assertGreater(len(anomaly_promos), 0, "Nenhuma promo de ID 218 encontrada")
        for p in anomaly_promos:
            if p.dispatch_methods == [DispatchMethod.TAKE_AWAY]:
                # Para in_store, ID 218 tem price=16.99 > original=16.64
                self.assertIsNone(p.original_price_cents)


if __name__ == "__main__":
    unittest.main()
