"""Testes unitários determinísticos para o DominosAdapter."""

from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from pizza_radar.adapters.dominos import (
    DominosAdapter,
    _extract_cents_from_text,
    _extract_discount_percentage,
)
from pizza_radar.core.adapter import NetworkError, ParseError
from pizza_radar.core.models import (
    Brand,
    DispatchMethod,
    DiscountType,
    OfferType,
    StoreScope,
    UnifiedPromo,
    Weekday,
)
from pizza_radar.core.validator import validate_promo
from pizza_radar.persistence.repository import SQLitePromotionRepository
from pizza_radar.pipeline.runner import run_pipeline

_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(filename: str) -> dict:
    path = os.path.join(_FIXTURES_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return json.loads(f.read(), parse_float=Decimal)


def _load_html_fixture(filename: str) -> str:
    path = os.path.join(_FIXTURES_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return f.read()


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

    def test_missing_mandatory_fields_raises_parse_error(self) -> None:
        """Item em combos.data sem id ou title emite ParseError explicitamente."""
        raw_missing_id = {
            "combos": {
                "data": [{"id": None, "title": "Sem ID"}]
            }
        }
        with self.assertRaises(ParseError) as ctx:
            self.adapter.parse(raw_missing_id, delivery_method="D")
        self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)

        raw_missing_title = {
            "combos": {
                "data": [{"id": 123, "title": ""}]
            }
        }
        with self.assertRaises(ParseError) as ctx:
            self.adapter.parse(raw_missing_title, delivery_method="D")
        self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)

        raw_non_dict_item = {
            "combos": {
                "data": ["not-a-dict"]
            }
        }
        with self.assertRaises(ParseError) as ctx:
            self.adapter.parse(raw_non_dict_item, delivery_method="D")
        self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)

    def test_error_propagation(self) -> None:
        """NetworkError e ParseError propagam com vendor correto."""
        with patch.object(self.adapter, "fetch_raw", side_effect=NetworkError("Timeout", vendor=Brand.DOMINOS)):
            with self.assertRaises(NetworkError) as ctx:
                self.adapter.fetch_promotions()
            self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)

    def test_parse_homepage_fixture(self) -> None:
        """Parse da homepage oficial extrai as 5 campanhas reais com combo-id."""
        html_content = _load_html_fixture("dominos_homepage.html")
        parsed = self.adapter.parse_homepage(html_content)
        self.assertEqual(len(parsed), 5)

        combo_ids = {item["combo_id"] for item in parsed}
        self.assertEqual(combo_ids, {"4742", "3397", "4464", "3423", "2468"})

        # Valida combo 4742 (Leiria 1=2, Takeaway)
        c4742 = next(c for c in parsed if c["combo_id"] == "4742")
        self.assertEqual(c4742["delivery_type"], "3")
        self.assertIn("1=2", c4742["title"])

        # Valida combo 3397 (Terças 50% desc, Ambos)
        c3397 = next(c for c in parsed if c["combo_id"] == "3397")
        self.assertEqual(c3397["delivery_type"], "1")
        self.assertEqual(c3397["discount_percentage"], 50.0)

        # Valida combo 4464 (Croissantíssima 9,99€, Ambos)
        c4464 = next(c for c in parsed if c["combo_id"] == "4464")
        self.assertEqual(c4464["delivery_type"], "1")
        self.assertEqual(c4464["price_cents"], 999)

        # Valida combo 3423 (Média desde 10,95€, Entrega)
        c3423 = next(c for c in parsed if c["combo_id"] == "3423")
        self.assertEqual(c3423["delivery_type"], "2")
        self.assertEqual(c3423["price_cents"], 1095)

        # Valida combo 2468 (30% desconto frangos, Ambos)
        c2468 = next(c for c in parsed if c["combo_id"] == "2468")
        self.assertEqual(c2468["delivery_type"], "1")
        self.assertEqual(c2468["discount_percentage"], 30.0)

    def test_adapt_homepage_items(self) -> None:
        """Adaptação de itens da homepage gera UnifiedPromo válidos com canais e tipos estritos."""
        html_content = _load_html_fixture("dominos_homepage.html")
        parsed = self.adapter.parse_homepage(html_content)

        all_promos = []
        for item in parsed:
            adapted = self.adapter.adapt_homepage(item, _observed_at())
            all_promos.extend(adapted)

        # 1 (takeaway) + 2 (ambos) + 2 (ambos) + 1 (delivery) + 2 (ambos) = 8 promos
        self.assertEqual(len(all_promos), 8)

        for p in all_promos:
            validate_promo(p)
            self.assertEqual(p.vendor, Brand.DOMINOS)
            self.assertEqual(p.store_scope, StoreScope.UNKNOWN)
            self.assertEqual(p.location_scope, "Lisboa")
            self.assertTrue(p.source_url.startswith("https://www.dominospizza.pt"))

        # Promoção de frango classificada como NON_PIZZA
        chicken_promos = [p for p in all_promos if "2468" in p.id]
        self.assertEqual(len(chicken_promos), 2)
        for cp in chicken_promos:
            self.assertEqual(cp.offer_type, OfferType.NON_PIZZA)

        # Terças de Perder a Cabeça mapeada para TUESDAY
        tuesday_promos = [p for p in all_promos if "3397" in p.id]
        self.assertEqual(len(tuesday_promos), 2)
        for tp in tuesday_promos:
            self.assertEqual(tp.days_of_week, [Weekday.TUESDAY])
            self.assertEqual(tp.discount_type, DiscountType.PERCENTAGE)

    def test_fetch_promotions_fallback_on_http_403(self) -> None:
        """HTTP 403 no endpoint ajax/order.php ativa fallback para Browserless e define FEATURED."""
        html_content = _load_html_fixture("dominos_homepage.html")

        # Simula HTTP 403 no fetch_raw
        http_403_err = NetworkError(
            "HTTP 403 Forbidden ao aceder a ajax/order.php",
            vendor=Brand.DOMINOS,
        )

        with patch.object(self.adapter, "fetch_raw", side_effect=http_403_err), \
             patch.object(self.adapter, "fetch_browserless_homepage", return_value=html_content):
            promos = self.adapter.fetch_promotions()

        self.assertEqual(len(promos), 8)
        self.assertEqual(self.adapter.coverage_level, "FEATURED")
        self.assertEqual(self.adapter.coverage_note, "Campanhas principais publicadas no site oficial")

    def test_fetch_promotions_does_not_fallback_on_parse_error(self) -> None:
        """ParseError no endpoint primário NÃO ativa fallback para não mascarar regressões."""
        with patch.object(self.adapter, "fetch_raw", return_value={"combos": {"data": [{"id": None}]}}):
            with self.assertRaises(ParseError) as ctx:
                self.adapter.fetch_promotions()
            self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)

    def test_fetch_promotions_does_not_fallback_on_generic_network_error(self) -> None:
        """Erro de rede não-403 (ex.: Connection Refused) não ativa fallback e propaga exceção."""
        net_err = NetworkError("Connection refused by target", vendor=Brand.DOMINOS)
        with patch.object(self.adapter, "fetch_raw", side_effect=net_err):
            with self.assertRaises(NetworkError) as ctx:
                self.adapter.fetch_promotions()
            self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)

    def test_parse_homepage_empty_raises_parse_error(self) -> None:
        """Homepage sem campanhas promocionais emite ParseError explicitamente."""
        with self.assertRaises(ParseError) as ctx:
            self.adapter.parse_homepage("<html><body>Sem campanhas</body></html>")
        self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)

    def test_fetch_browserless_homepage_success(self) -> None:
        """Browserless devolve HTML oficial da homepage com HTTP 200 e combos válidos."""
        html_fixture = _load_html_fixture("dominos_homepage.html")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {"X-Response-Code": "200"}
        mock_resp.read.return_value = html_fixture.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with patch.dict(os.environ, {"BROWSERLESS_API_KEY": "test-key-12345"}), \
             patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result_html = self.adapter.fetch_browserless_homepage()

        self.assertIn("combo-id", result_html)
        self.assertIn("Domino", result_html)

        # Verificar se o pedido incluiu cabeçalho Authorization com Bearer
        self.assertTrue(mock_urlopen.called)
        req_sent = mock_urlopen.call_args[0][0]
        self.assertEqual(req_sent.headers.get("Authorization"), "Bearer test-key-12345")
        self.assertEqual(req_sent.headers.get("Cache-control"), "no-cache")

    def test_fetch_browserless_homepage_missing_api_key(self) -> None:
        """Ausência de BROWSERLESS_API_KEY emite NetworkError explícito com vendor=DOMINOS."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(NetworkError) as ctx:
                self.adapter.fetch_browserless_homepage()
            self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)
            self.assertIn("BROWSERLESS_API_KEY", str(ctx.exception))

    def test_fetch_browserless_homepage_http_errors(self) -> None:
        """Erros HTTP 401, 429 e 500 da Browserless emitem NetworkError sem expor chaves."""
        for code in (401, 429, 500):
            err = urllib.error.HTTPError(
                url="https://production-lon.browserless.io/content",
                code=code,
                msg=f"Error {code}",
                hdrs={},
                fp=io.BytesIO(b"error details"),
            )
            with patch.dict(os.environ, {"BROWSERLESS_API_KEY": "test-key"}), \
                 patch("urllib.request.urlopen", side_effect=err):
                with self.assertRaises(NetworkError) as ctx:
                    self.adapter.fetch_browserless_homepage()
                self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)
                self.assertIn(f"HTTP {code}", str(ctx.exception))
                self.assertNotIn("test-key", str(ctx.exception))

    def test_fetch_browserless_homepage_target_403(self) -> None:
        """Se o target responder HTTP 403 através da Browserless, emite NetworkError."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {"X-Response-Code": "403"}
        mock_resp.read.return_value = b"<html>Forbidden</html>"
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with patch.dict(os.environ, {"BROWSERLESS_API_KEY": "test-key"}), \
             patch("urllib.request.urlopen", return_value=mock_resp):
            with self.assertRaises(NetworkError) as ctx:
                self.adapter.fetch_browserless_homepage()
            self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)
            self.assertIn("403", str(ctx.exception))

    def test_fetch_browserless_homepage_cloudflare_challenge(self) -> None:
        """Se o HTML devolvido for uma página de desafio Cloudflare, emite NetworkError."""
        challenge_html = "<html><head><title>Just a moment...</title></head><body>Verify you are human</body></html>"
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {"X-Response-Code": "200"}
        mock_resp.read.return_value = challenge_html.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with patch.dict(os.environ, {"BROWSERLESS_API_KEY": "test-key"}), \
             patch("urllib.request.urlopen", return_value=mock_resp):
            with self.assertRaises(NetworkError) as ctx:
                self.adapter.fetch_browserless_homepage()
            self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)
            self.assertIn("Just a moment...", str(ctx.exception))

    def test_fetch_browserless_homepage_missing_combo_id(self) -> None:
        """Se o HTML não contiver atributos combo-id, emite ParseError determinístico."""
        empty_html = "<html><head><title>Domino's Pizza</title></head><body>Sem ofertas</body></html>"
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {"X-Response-Code": "200"}
        mock_resp.read.return_value = empty_html.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with patch.dict(os.environ, {"BROWSERLESS_API_KEY": "test-key"}), \
             patch("urllib.request.urlopen", return_value=mock_resp):
            with self.assertRaises(ParseError) as ctx:
                self.adapter.fetch_browserless_homepage()
            self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)
            self.assertIn("combo-id", str(ctx.exception))

    def test_data_preservation_on_browserless_failure(self) -> None:
        """Em caso de falha da Browserless, a pipeline preserva as ofertas ativas existentes na BD."""
        repo = SQLitePromotionRepository(":memory:")

        # Insere uma promoção pré-existente da Domino's
        existing_promo = UnifiedPromo(
            id="dom_4742_delivery",
            vendor=Brand.DOMINOS,
            title="Promoção Existente Preservada",
            description="Descrição válida",
            observed_at=datetime.now(timezone.utc).isoformat(),
            price_cents=1095,
            discount_type=DiscountType.SPECIAL_MENU,
            dispatch_methods=[DispatchMethod.DELIVERY],
            store_scope=StoreScope.SPECIFIC_STORES,
            store_ids=["140"],
            store_names=["Areeiro"],
            location_scope="Lisboa",
            offer_type=OfferType.PIZZA,
        )
        repo.upsert_promotions([existing_promo], vendor=Brand.DOMINOS)

        # Simula falha do adaptador da Domino's (HTTP 403 no endpoint primário + falha na Browserless)
        with patch.object(self.adapter, "fetch_promotions", side_effect=NetworkError("Browserless indisponível", vendor=Brand.DOMINOS)):
            result = run_pipeline(
                repo=repo,
                adapters=[self.adapter],
                data_mode="demo",
            )

        # O estado de sync da Domino's é FAILED
        self.assertEqual(result.vendor_results["DOMINOS"].status, "FAILED")

        # As ofertas ativas pré-existentes permanecem intocadas na base de dados
        active_promos = repo.get_active_promotions(location_scope="Lisboa")
        self.assertEqual(len(active_promos), 1)
        self.assertEqual(active_promos[0].id, "dom_4742_delivery")

        row = repo._get_connection().execute(
            "SELECT consecutive_misses FROM promotions WHERE id = ?",
            ("dom_4742_delivery",),
        ).fetchone()
        self.assertEqual(row["consecutive_misses"], 0)


if __name__ == "__main__":
    unittest.main()
