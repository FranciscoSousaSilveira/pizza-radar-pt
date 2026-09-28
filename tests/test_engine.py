"""Testes unitários exaustivos para o motor determinístico (Issue #10).

Cobre:
  - Identidade persistente estável vs. agrupamento visual vs. variantes de loja.
  - Invariância do ID de histórico quando lojas divergem ou convergem em preço.
  - Ausência total de cartões repetidos no agrupamento visual.
  - Rankings separados e explicáveis:
      * Melhor preço por pizza (BEST_UNIT_PRICE);
      * Maior percentagem de desconto (HIGHEST_DISCOUNT);
      * Menor preço absoluto (LOWEST_ABSOLUTE_PRICE);
      * Mais recentes (RECENTLY_OBSERVED).
  - Filtros determinísticos (marca, canal, loja, dia da semana, faixa de preço, comparabilidade).
  - Tratamento estrito de dados incompletos (zero valores inventados).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from pizza_radar.core.models import (
    Brand,
    DiscountType,
    DispatchMethod,
    PizzaSize,
    StoreScope,
    UnifiedPromo,
    Weekday,
)
from pizza_radar.engine.filters import (
    filter_by_brand,
    filter_by_dispatch_method,
    filter_by_price_range,
    filter_by_store,
    filter_by_weekday,
    filter_comparable_only,
)
from pizza_radar.engine.identity import (
    StoreVariant,
    VisualPromoGroup,
    build_persistent_promo_id,
    extract_canonical_campaign_id,
    group_promos_for_visual_presentation,
)
from pizza_radar.engine.rankings import (
    RankingCriteria,
    rank_by_discount,
    rank_by_lowest_price,
    rank_by_recently_observed,
    rank_by_unit_price,
)


def _make_promo(
    promo_id: str,
    vendor: Brand = Brand.PAPA_JOHNS,
    title: str = "Promo Teste",
    price_cents: int | None = 1500,
    original_price_cents: int | None = 2000,
    pizza_count: int | None = 2,
    pizza_size: PizzaSize = PizzaSize.MEDIUM,
    store_ids: list[str] | None = None,
    dispatch_methods: list[DispatchMethod] | None = None,
    days_of_week: list[Weekday] | None = None,
    observed_at: str = "2026-09-28T16:00:00+01:00",
) -> UnifiedPromo:
    return UnifiedPromo(
        id=promo_id,
        vendor=vendor,
        title=title,
        description=f"Descrição de {title}",
        observed_at=observed_at,
        price_cents=price_cents,
        original_price_cents=original_price_cents,
        store_scope=StoreScope.SPECIFIC_STORES,
        store_ids=store_ids or ["2"],
        store_names=["Amoreiras"],
        pizza_count=pizza_count,
        pizza_size=pizza_size,
        dispatch_methods=dispatch_methods or [DispatchMethod.TAKE_AWAY],
        days_of_week=days_of_week or [],
        source_url="https://papajohns.pt/promocoes/",
        location_scope="Lisboa",
    )


# ===========================================================================
# 1. Testes de Identidade Persistente vs Agrupamento Visual
# ===========================================================================

class TestPersistentIdentityAndGrouping(unittest.TestCase):
    """Testa a estabilidade do ID de histórico e ausência de cartões duplicados."""

    def test_extract_canonical_campaign_id(self) -> None:
        """Extrai o identificador puro da campanha de vários formatos de ID."""
        self.assertEqual(extract_canonical_campaign_id("pj_223_in_store"), "223")
        self.assertEqual(extract_canonical_campaign_id("pj_223_in_store_2_13"), "223")
        self.assertEqual(extract_canonical_campaign_id("dom_lunch_deal_delivery"), "lunch")
        self.assertEqual(extract_canonical_campaign_id("simple_id"), "simple_id")

    def test_persistent_promo_id_is_stable_over_time(self) -> None:
        """O ID persistente de histórico é invariante mesmo que lojas divirjam em preço."""
        pid_uniform = build_persistent_promo_id(Brand.PAPA_JOHNS, "223", DispatchMethod.TAKE_AWAY)
        pid_diverged = build_persistent_promo_id(Brand.PAPA_JOHNS, "223", DispatchMethod.TAKE_AWAY)
        self.assertEqual(pid_uniform, pid_diverged)
        self.assertEqual(pid_uniform, "pid_papa_johns_223_take_away")

    def test_visual_grouping_no_duplicate_cards(self) -> None:
        """Múltiplas variantes da mesma oferta agrupam num único VisualPromoGroup."""
        # Suponha que loja 2 e 13 têm preço 1798 e loja 3 tem preço 1998
        promo_a = _make_promo("pj_223_in_store_2_13", price_cents=1798, store_ids=["2", "13"])
        promo_b = _make_promo("pj_223_in_store_3", price_cents=1998, store_ids=["3"])

        groups = group_promos_for_visual_presentation([promo_a, promo_b])

        # O frontend recebe exatamente 1 cartão (VisualPromoGroup)
        self.assertEqual(len(groups), 1)
        vg = groups[0]
        self.assertEqual(vg.persistent_id, "pid_papa_johns_223_take_away")
        self.assertFalse(vg.has_uniform_price)
        self.assertEqual(vg.min_price_cents, 1798)
        self.assertEqual(vg.max_price_cents, 1998)
        self.assertEqual(vg.display_price_label, "Desde 17,98€")
        self.assertEqual(vg.all_store_ids, ["2", "3", "13"])
        self.assertEqual(len(vg.variants), 2)

    def test_visual_grouping_uniform_price(self) -> None:
        """Quando todas as lojas têm o mesmo preço, exibe preço único."""
        promo = _make_promo("pj_223_in_store", price_cents=1798, store_ids=["2", "3", "13"])
        groups = group_promos_for_visual_presentation([promo])

        self.assertEqual(len(groups), 1)
        vg = groups[0]
        self.assertTrue(vg.has_uniform_price)
        self.assertEqual(vg.display_price_label, "17,98€")

    def test_visual_grouping_separates_channels(self) -> None:
        """Takeaway e Delivery para a mesma campanha geram 2 cartões visuais distintos."""
        takeaway = _make_promo("pj_223_in_store", price_cents=1798, dispatch_methods=[DispatchMethod.TAKE_AWAY])
        delivery = _make_promo("pj_223_pj_delivery", price_cents=2098, dispatch_methods=[DispatchMethod.DELIVERY])

        groups = group_promos_for_visual_presentation([takeaway, delivery])
        self.assertEqual(len(groups), 2)
        pids = {g.persistent_id for g in groups}
        self.assertIn("pid_papa_johns_223_take_away", pids)
        self.assertIn("pid_papa_johns_223_delivery", pids)


# ===========================================================================
# 2. Testes de Rankings Determinísticos e Explicáveis
# ===========================================================================

class TestDeterministicRankings(unittest.TestCase):
    """Testa os quatro algoritmos de ranking objetivos e suas explicações."""

    def setUp(self) -> None:
        # Promo 1: 2 pizzas por 15,00€ -> 7,50€ / pizza (comparável)
        self.p1 = _make_promo("p1", title="Duo 15", price_cents=1500, pizza_count=2, original_price_cents=2000)
        # Promo 2: 3 pizzas por 21,00€ -> 7,00€ / pizza (melhor unitário)
        self.p2 = _make_promo("p2", title="Trio 21", price_cents=2100, pizza_count=3, original_price_cents=3000)
        # Promo 3: Combo sem pizza_count especificado (não comparável)
        self.p3 = _make_promo("p3", title="Menu Secreto", price_cents=599, pizza_count=None, original_price_cents=1000)
        # Promo 4: 1 pizza por 8,00€ com 50% desconto (800 / 1600)
        self.p4 = _make_promo("p4", title="50% Off", price_cents=800, pizza_count=1, original_price_cents=1600)

    def test_rank_by_unit_price(self) -> None:
        """Ordena pelo menor preço por pizza e exclui ofertas não comparáveis."""
        ranked = rank_by_unit_price([self.p1, self.p2, self.p3, self.p4])

        # p3 deve ser excluído porque pizza_count é None
        self.assertEqual(len(ranked), 3)

        # 1º lugar: p2 (7,00€ / pizza)
        self.assertEqual(ranked[0].rank, 1)
        self.assertEqual(ranked[0].promo_id, "p2")
        self.assertEqual(ranked[0].score, 700)
        self.assertIn("7,00€ por pizza", ranked[0].explanation)

        # 2º lugar: p1 (7,50€ / pizza)
        self.assertEqual(ranked[1].rank, 2)
        self.assertEqual(ranked[1].promo_id, "p1")
        self.assertEqual(ranked[1].score, 750)
        self.assertIn("7,50€ por pizza", ranked[1].explanation)

        # 3º lugar: p4 (8,00€ / pizza)
        self.assertEqual(ranked[2].rank, 3)
        self.assertEqual(ranked[2].promo_id, "p4")
        self.assertEqual(ranked[2].score, 800)

    def test_rank_by_discount(self) -> None:
        """Ordena pela maior percentagem de desconto comprovada."""
        # p4: (1600 - 800) / 1600 = 50.0%
        # p3: (1000 - 599) / 1000 = 40.1%
        # p2: (3000 - 2100) / 3000 = 30.0%
        # p1: (2000 - 1500) / 2000 = 25.0%
        ranked = rank_by_discount([self.p1, self.p2, self.p3, self.p4])

        self.assertEqual(len(ranked), 4)
        self.assertEqual(ranked[0].promo_id, "p4")
        self.assertAlmostEqual(ranked[0].score, 50.0, places=1)
        self.assertIn("50,0% de desconto", ranked[0].explanation)
        self.assertIn("Poupança de 8,00€", ranked[0].explanation)

        self.assertEqual(ranked[1].promo_id, "p3")
        self.assertEqual(ranked[2].promo_id, "p2")
        self.assertEqual(ranked[3].promo_id, "p1")

    def test_rank_by_lowest_price(self) -> None:
        """Ordena pelo menor valor absoluto total (menor desembolso)."""
        ranked = rank_by_lowest_price([self.p1, self.p2, self.p3, self.p4])

        self.assertEqual(len(ranked), 4)
        # Menor preço: p3 (5,99€)
        self.assertEqual(ranked[0].promo_id, "p3")
        self.assertEqual(ranked[0].score, 599)
        self.assertIn("5,99€", ranked[0].explanation)

        # 2º: p4 (8,00€)
        self.assertEqual(ranked[1].promo_id, "p4")
        self.assertEqual(ranked[1].score, 800)

        # 3º: p1 (15,00€)
        self.assertEqual(ranked[2].promo_id, "p1")

        # 4º: p2 (21,00€)
        self.assertEqual(ranked[3].promo_id, "p2")

    def test_rank_by_recently_observed(self) -> None:
        """Ordena por data de observação decrescente."""
        older = _make_promo("old", observed_at="2026-09-01T10:00:00+00:00")
        newer = _make_promo("new", observed_at="2026-09-28T18:00:00+00:00")

        ranked = rank_by_recently_observed([older, newer])
        self.assertEqual(ranked[0].promo_id, "new")
        self.assertEqual(ranked[1].promo_id, "old")


# ===========================================================================
# 3. Testes de Filtros Determinísticos
# ===========================================================================

class TestFilters(unittest.TestCase):
    """Testa os filtros de pesquisa de promoções."""

    def setUp(self) -> None:
        self.pj = _make_promo("pj1", vendor=Brand.PAPA_JOHNS, store_ids=["2"], dispatch_methods=[DispatchMethod.TAKE_AWAY], price_cents=1000)
        self.tele = _make_promo("tp1", vendor=Brand.TELEPIZZA, store_ids=["10"], dispatch_methods=[DispatchMethod.DELIVERY], price_cents=1500)
        self.dom = _make_promo("dm1", vendor=Brand.DOMINOS, store_ids=["140"], dispatch_methods=[DispatchMethod.TAKE_AWAY], price_cents=2000, days_of_week=[Weekday.MONDAY])

    def test_filter_by_brand(self) -> None:
        """Filtra ofertas por marca específica."""
        result = filter_by_brand([self.pj, self.tele, self.dom], Brand.PAPA_JOHNS)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "pj1")

    def test_filter_by_dispatch_method(self) -> None:
        """Filtra ofertas por canal de entrega."""
        takeaway = filter_by_dispatch_method([self.pj, self.tele, self.dom], DispatchMethod.TAKE_AWAY)
        self.assertEqual(len(takeaway), 2)
        delivery = filter_by_dispatch_method([self.pj, self.tele, self.dom], DispatchMethod.DELIVERY)
        self.assertEqual(len(delivery), 1)
        self.assertEqual(delivery[0].id, "tp1")

    def test_filter_by_store(self) -> None:
        """Filtra ofertas por elegibilidade de loja."""
        store_2 = filter_by_store([self.pj, self.tele, self.dom], "2")
        self.assertEqual(len(store_2), 1)
        self.assertEqual(store_2[0].id, "pj1")

    def test_filter_by_weekday(self) -> None:
        """Filtra ofertas elegíveis num determinado dia da semana."""
        # dm1 é apenas às segundas; pj e tele não têm restrição de dia (válidas todos os dias)
        monday_promos = filter_by_weekday([self.pj, self.tele, self.dom], Weekday.MONDAY)
        self.assertEqual(len(monday_promos), 3)

        tuesday_promos = filter_by_weekday([self.pj, self.tele, self.dom], Weekday.TUESDAY)
        self.assertEqual(len(tuesday_promos), 2)
        self.assertNotIn(self.dom, tuesday_promos)

    def test_filter_by_price_range(self) -> None:
        """Filtra ofertas dentro de um intervalo de preço."""
        mid_range = filter_by_price_range([self.pj, self.tele, self.dom], min_cents=1200, max_cents=1800)
        self.assertEqual(len(mid_range), 1)
        self.assertEqual(mid_range[0].id, "tp1")

    def test_filter_comparable_only(self) -> None:
        """Filtra estritamente itens comparáveis."""
        comp = _make_promo("comp", price_cents=1000, pizza_count=1)
        non_comp = _make_promo("non_comp", price_cents=1000, pizza_count=None)

        result = filter_comparable_only([comp, non_comp])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "comp")


if __name__ == "__main__":
    unittest.main()
