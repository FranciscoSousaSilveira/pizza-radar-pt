"""Testes de isolamento de falhas entre adaptadores de diferentes marcas.

Verifica o requisito: 'falha de uma marca não deve corromper as restantes'.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from pizza_radar.adapters.dominos import DominosAdapter
from pizza_radar.adapters.papa_johns import PapaJohnsAdapter
from pizza_radar.adapters.pizza_hut import PizzaHutAdapter
from pizza_radar.adapters.telepizza import TelepizzaAdapter
from pizza_radar.core.adapter import NetworkError, ParseError
from pizza_radar.core.models import Brand, UnifiedPromo


def _run_all_adapters_safely(adapters: list) -> tuple[list[UnifiedPromo], dict[Brand, Exception]]:
    """Função utilitária que simula a orquestração segura e isolada de múltiplos adaptadores.

    Garante que a falha de um adaptador não impede os restantes de executar e devolver resultados.
    """
    results: list[UnifiedPromo] = []
    errors: dict[Brand, Exception] = {}

    for adapter in adapters:
        try:
            promos = adapter.fetch_promotions()
            results.extend(promos)
        except (NetworkError, ParseError) as exc:
            errors[adapter.vendor] = exc

    return results, errors


class TestAdaptersIsolation(unittest.TestCase):
    """Testa o isolamento de falhas entre os adaptadores."""

    def test_single_vendor_network_failure_does_not_affect_others(self) -> None:
        """Falha de rede na Domino's permite que Papa John's, Telepizza e Pizza Hut funcionem."""
        pj = PapaJohnsAdapter()
        dom = DominosAdapter()
        tele = TelepizzaAdapter()
        ph = PizzaHutAdapter()

        fake_promo = MagicMock(spec=UnifiedPromo)

        # Simular Papa John's com sucesso, Domino's com NetworkError, Telepizza com sucesso
        with patch.object(pj, "fetch_promotions", return_value=[fake_promo]), \
             patch.object(dom, "fetch_promotions", side_effect=NetworkError("Domino's timeout", vendor=Brand.DOMINOS)), \
             patch.object(tele, "fetch_promotions", return_value=[fake_promo, fake_promo]), \
             patch.object(ph, "fetch_promotions", return_value=[fake_promo]):

            promos, errors = _run_all_adapters_safely([pj, dom, tele, ph])

        # 4 promoções recolhidas com sucesso dos 3 fornecedores operacionais
        self.assertEqual(len(promos), 4)
        # Erro isolado exclusivamente na Domino's
        self.assertIn(Brand.DOMINOS, errors)
        self.assertIsInstance(errors[Brand.DOMINOS], NetworkError)
        self.assertEqual(errors[Brand.DOMINOS].vendor, Brand.DOMINOS)
        self.assertNotIn(Brand.PAPA_JOHNS, errors)
        self.assertNotIn(Brand.TELEPIZZA, errors)
        self.assertNotIn(Brand.PIZZA_HUT, errors)

    def test_single_vendor_parse_failure_does_not_affect_others(self) -> None:
        """Erro de parsing na Telepizza não afeta Domino's nem Pizza Hut."""
        dom = DominosAdapter()
        tele = TelepizzaAdapter()
        ph = PizzaHutAdapter()

        fake_promo = MagicMock(spec=UnifiedPromo)

        with patch.object(dom, "fetch_promotions", return_value=[fake_promo]), \
             patch.object(tele, "fetch_promotions", side_effect=ParseError("HTML alterado", vendor=Brand.TELEPIZZA)), \
             patch.object(ph, "fetch_promotions", return_value=[fake_promo]):

            promos, errors = _run_all_adapters_safely([dom, tele, ph])

        self.assertEqual(len(promos), 2)
        self.assertIn(Brand.TELEPIZZA, errors)
        self.assertIsInstance(errors[Brand.TELEPIZZA], ParseError)
        self.assertNotIn(Brand.DOMINOS, errors)
        self.assertNotIn(Brand.PIZZA_HUT, errors)


if __name__ == "__main__":
    unittest.main()
