"""Testes unitários de resiliência por item e fiabilidade de rede em CI/CD (Issue #24).

Invariantes de Engenharia:
1. Uma oferta individual malformada ou sem canal nunca invalida a marca inteira.
2. Registos de warning estruturados são emitidos para itens ignorados.
3. Se todas as ofertas do payload forem inválidas, ParseError é propagado explicitamente.
4. Domino's gere sessão de cookies legítima e isola HTTP 403 em NetworkError.
5. Telepizza executa retries determinísticos em falhas transitórias de conexão.
"""

from __future__ import annotations

import http.client
import urllib.error
from unittest.mock import MagicMock, patch
import unittest

from pizza_radar.adapters.dominos import DominosAdapter
from pizza_radar.adapters.pizza_hut import PizzaHutAdapter
from pizza_radar.adapters.telepizza import TelepizzaAdapter
from pizza_radar.core.adapter import NetworkError, ParseError
from pizza_radar.core.models import Brand, DispatchMethod


class TestPizzaHutItemResilience(unittest.TestCase):
    """Testa a tolerância a falhas por item no adaptador da Pizza Hut."""

    def setUp(self) -> None:
        self.adapter = PizzaHutAdapter()

    def test_item_without_channel_is_skipped_and_valid_items_preserved(self) -> None:
        """Item sem canal comprovado (ex.: oferta 15056) é ignorado sem invalidar ofertas válidas."""
        raw_items = [
            # Item 1: Válido Take Away
            {
                "id": 101,
                "slug": "menu-duo-tw",
                "title": {"rendered": "Menu Duo Take Away 14,95€"},
                "link": "https://www.pizzahut.pt/ofertas/menu-duo-tw/",
            },
            # Item 2: Sem canal comprovado (deve ser ignorado com warning)
            {
                "id": 15056,
                "slug": "dlsc6eur",
                "title": {"rendered": "Oferta Especial Sem Canal"},
                "link": "https://www.pizzahut.pt/ofertas/dlsc6eur/",
            },
            # Item 3: Sem título (deve ser ignorado com warning)
            {
                "id": 103,
                "slug": "invalido",
                "title": {"rendered": ""},
            },
            # Item 4: Válido Delivery
            {
                "id": 104,
                "slug": "menu-familia-dlv",
                "title": {"rendered": "Menu Família Entrega 22,50€"},
                "link": "https://www.pizzahut.pt/ofertas/menu-familia-dlv/",
            },
        ]

        parsed = self.adapter.parse(raw_items)

        # Apenas os 2 válidos são extraídos
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["id"], "101")
        self.assertIn(DispatchMethod.TAKE_AWAY, parsed[0]["dispatch_methods"])
        self.assertEqual(parsed[1]["id"], "104")
        self.assertIn(DispatchMethod.DELIVERY, parsed[1]["dispatch_methods"])

    def test_parse_raises_error_if_all_items_are_invalid(self) -> None:
        """Se o array tinha itens mas nenhum pôde ser aproveitado, lança ParseError."""
        raw_items = [
            {"id": 999, "slug": "desconhecido", "title": {"rendered": "Oferta Sem Canal"}},
            {"id": None, "title": {"rendered": "Sem ID"}},
        ]
        with self.assertRaises(ParseError) as ctx:
            self.adapter.parse(raw_items)
        self.assertEqual(ctx.exception.vendor, Brand.PIZZA_HUT)


class TestDominosResilienceAndSession(unittest.TestCase):
    """Testa a resiliência e a gestão de sessão da Domino's."""

    def setUp(self) -> None:
        self.adapter = DominosAdapter()

    def test_item_level_resilience_in_combos(self) -> None:
        """Itens malformados no array de combos são ignorados preservando os válidos."""
        raw_payload = {
            "combos": {
                "data": [
                    # Combo 1: Válido
                    {"id": "2420", "title": "MÉDIA DESDE 10,95€", "description": "1 pizza média"},
                    # Combo 2: Inválido (sem id)
                    {"id": "", "title": "Combo Sem ID"},
                    # Combo 3: Inválido (não é dict)
                    "string_invalida",
                    # Combo 4: Válido
                    {"id": "2425", "title": "MENU DUETO 15,95€", "description": "2 pizzas médias"},
                ]
            }
        }
        parsed = self.adapter.parse(raw_payload, delivery_method="D")
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["id"], "2420")
        self.assertEqual(parsed[1]["id"], "2425")

    def test_parse_raises_if_all_combos_invalid(self) -> None:
        """Se nenhum combo for válido, ParseError é lançado."""
        raw_payload = {
            "combos": {
                "data": [
                    {"id": None, "title": "Invalido"},
                    {"id": "123", "title": ""},
                ]
            }
        }
        with self.assertRaises(ParseError) as ctx:
            self.adapter.parse(raw_payload)
        self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)

    def test_http_403_raises_clear_network_error(self) -> None:
        """HTTP 403 Forbidden é capturado e transformado em NetworkError explícito."""
        mock_opener = MagicMock()
        mock_opener.open.side_effect = urllib.error.HTTPError(
            url="https://www.dominospizza.pt/ajax/order.php",
            code=403,
            msg="Forbidden",
            hdrs=None,  # type: ignore
            fp=None,
        )
        adapter = DominosAdapter(opener=mock_opener)

        with self.assertRaises(NetworkError) as ctx:
            adapter.fetch_raw()

        self.assertEqual(ctx.exception.vendor, Brand.DOMINOS)
        self.assertIn("HTTP 403 Forbidden", str(ctx.exception))
        self.assertIn("Cloudflare/ASN", str(ctx.exception))


class TestTelepizzaResilienceAndRetries(unittest.TestCase):
    """Testa a resiliência por item e retries do adaptador da Telepizza."""

    def setUp(self) -> None:
        self.adapter = TelepizzaAdapter()

    def test_item_level_resilience_in_html_cards(self) -> None:
        """Cartões sem canal ou id são ignorados sem invalidar os cartões válidos."""
        html_content = """
        <div class="offers-container">
            <!-- Cartão 1: Válido Entrega -->
            <div class="offer-tile__wrap" data-tab-content="delivery">
                <a class="offer-tile__btn" data-id="tp_01" data-name="2 Médias por 14,95€" data-detail="Massa fina"></a>
            </div>
            <!-- Cartão 2: Sem canal comprovado (aba desconhecida e sem palavras-chave) -->
            <div class="offer-tile__wrap" data-tab-content="desconhecido">
                <a class="offer-tile__btn" data-id="tp_sem_canal" data-name="Promocao Misterio" data-detail="Apenas hoje"></a>
            </div>
            <!-- Cartão 3: Sem id -->
            <div class="offer-tile__wrap" data-tab-content="takeaway">
                <a class="offer-tile__btn" data-id="" data-name="Take Away Barato"></a>
            </div>
            <!-- Cartão 4: Válido Take Away -->
            <div class="offer-tile__wrap" data-tab-content="takeaway">
                <a class="offer-tile__btn" data-id="tp_02" data-name="Pizza Individual 7,95€" data-detail="Levantamento em loja"></a>
            </div>
        </div>
        """
        parsed = self.adapter.parse(html_content)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["id"], "tp_01")
        self.assertIn("delivery", parsed[0]["channels"])
        self.assertEqual(parsed[1]["id"], "tp_02")
        self.assertIn("takeaway", parsed[1]["channels"])

    def test_parse_raises_if_all_cards_invalid(self) -> None:
        """Se o HTML contém cartões mas nenhum é válido, emite ParseError."""
        html_content = """
        <div class="offer-tile__wrap" data-tab-content="none">
            <a class="offer-tile__btn" data-id="invalido" data-name="Sem canal"></a>
        </div>
        """
        with self.assertRaises(ParseError) as ctx:
            self.adapter.parse(html_content)
        self.assertEqual(ctx.exception.vendor, Brand.TELEPIZZA)

    @patch("urllib.request.urlopen")
    @patch("time.sleep")
    def test_retries_transient_disconnection_until_success(
        self,
        mock_sleep: MagicMock,
        mock_urlopen: MagicMock,
    ) -> None:
        """Falhas transitórias como RemoteDisconnected sofrem retry com sucesso."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html><div class='offer-tile__wrap'></div></html>"
        mock_resp.__enter__.return_value = mock_resp

        # Falha 2 vezes com RemoteDisconnected e tem sucesso na 3ª tentativa
        mock_urlopen.side_effect = [
            http.client.RemoteDisconnected("Remote end closed connection without response"),
            http.client.RemoteDisconnected("Remote end closed connection without response"),
            mock_resp,
        ]

        result = self.adapter.fetch_raw(max_retries=3)
        self.assertIn("offer-tile__wrap", result)
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("urllib.request.urlopen")
    @patch("time.sleep")
    def test_retries_exhausted_raises_network_error(
        self,
        mock_sleep: MagicMock,
        mock_urlopen: MagicMock,
    ) -> None:
        """Se as 3 tentativas falharem, NetworkError é propagado."""
        mock_urlopen.side_effect = ConnectionResetError("Connection reset by peer")

        with self.assertRaises(NetworkError) as ctx:
            self.adapter.fetch_raw(max_retries=3)

        self.assertEqual(ctx.exception.vendor, Brand.TELEPIZZA)
        self.assertIn("Falha após 3 tentativas", str(ctx.exception))
        self.assertEqual(mock_urlopen.call_count, 3)


if __name__ == "__main__":
    unittest.main()
