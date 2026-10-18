"""Testes unitários determinísticos para o bot de alertas do Telegram."""

import io
import json
import unittest
from unittest.mock import MagicMock, patch

from pizza_radar.core.models import Brand, OfferType, UnifiedPromo
from pizza_radar.notifications.telegram_bot import (
    TelegramDispatchResult,
    dispatch_daily_highlights,
    format_telegram_alert_message,
    select_daily_highlights,
)


class TestTelegramBot(unittest.TestCase):
    """Testa a seleção de destaques, formatação e despacho de alertas."""

    def setUp(self):
        self.sample_promos = [
            {
                "vendor": "DOMINOS",
                "title": "Mega Semana 2x1 Médias",
                "min_price_cents": 1200,
                "max_discount_percentage": 50.0,
                "min_price_per_pizza_cents": 600,
                "source_url": "https://www.dominospizza.pt/promocoes",
                "offer_type": "PIZZA",
            },
            {
                "vendor": "PAPA_JOHNS",
                "title": "Pizza Individual Almoço",
                "min_price_cents": 595,
                "max_discount_percentage": 30.0,
                "min_price_per_pizza_cents": 595,
                "source_url": "https://www.papajohns.pt/promocoes",
                "offer_type": "PIZZA",
            },
            {
                "vendor": "PIZZA_HUT",
                "title": "Super Rodízio Lisboa",
                "min_price_cents": 1500,
                "max_discount_percentage": 40.0,
                "min_price_per_pizza_cents": None,
                "source_url": "https://www.pizzahut.pt/ofertas",
                "offer_type": "PIZZA",
            },
            {
                "vendor": "TELEPIZZA",
                "title": "Asinhas de Frango",
                "min_price_cents": 350,
                "max_discount_percentage": 10.0,
                "min_price_per_pizza_cents": None,
                "source_url": "https://www.telepizza.pt/promocoes",
                "offer_type": "NON_PIZZA",  # Não deve ser selecionado para destaque de pizza
            },
        ]

    def test_select_daily_highlights_filters_non_pizza_and_selects_top_3(self):
        """Garante que apenas pizzas são consideradas e seleciona top 3 por critérios distintos."""
        highlights = select_daily_highlights(self.sample_promos, limit=3)
        self.assertEqual(len(highlights), 3)

        # O item NON_PIZZA (asinhas) não pode estar presente
        titles = [h["title"] for h in highlights]
        self.assertNotIn("Asinhas de Frango", titles)

        # Top discount: 50% (Domino's)
        self.assertEqual(highlights[0]["vendor"], "DOMINOS")
        self.assertEqual(highlights[0]["discount_pct"], 50)

    def test_format_telegram_alert_message(self):
        """Verifica a estrutura e formatação da mensagem Markdown."""
        highlights = select_daily_highlights(self.sample_promos, limit=2)
        message = format_telegram_alert_message(highlights)

        self.assertIn("🍕 *PIZZA RADAR LISBOA — DESTAQUES DO DIA*", message)
        self.assertIn("Domino's Pizza", message)
        self.assertIn("12,00 €", message)
        self.assertIn("(-50%)", message)
        self.assertIn("6,00 € / pizza", message)
        self.assertIn("https://pizzaradar.pt", message)

    def test_dispatch_simulation_mode_when_tokens_missing(self):
        """Em ambiente sem variáveis de ambiente, executa em modo simulação sem erros de rede."""
        with patch.dict("os.environ", {}, clear=True):
            result = dispatch_daily_highlights(self.sample_promos, bot_token="", chat_id="")
            self.assertTrue(result.success)
            self.assertEqual(result.mode, "simulated")
            self.assertIn("PIZZA RADAR LISBOA", result.message_text)

    @patch("urllib.request.urlopen")
    def test_dispatch_real_call_with_tokens(self, mock_urlopen):
        """Verifica o disparo real via Telegram Bot API com mock de HTTP POST."""
        fake_response = io.BytesIO(b'{"ok": true, "result": {"message_id": 999}}')
        fake_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = fake_response

        result = dispatch_daily_highlights(
            self.sample_promos,
            bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            chat_id="-1001234567890",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.mode, "sent")
        self.assertEqual(result.response_status, 200)
        self.assertEqual(result.chat_id, "-1001234567890")
        mock_urlopen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
