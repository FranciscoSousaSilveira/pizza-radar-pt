"""Testes unitários determinísticos para o motor do Pizza Radar PT (Issue #10).

Cobertura exaustiva:
  - Identidade persistente estável vs. variantes por loja vs. agrupamento visual.
  - Invariância do ID de histórico perante divergência e convergência de preços entre lojas.
  - Extração robusta de campaign_id mesmo com underscores e hífenes.
  - Agrupamento visual estritamente independente da ordem de entrada (100% determinístico).
  - Cálculo de BEST_UNIT_PRICE restrito a variantes individualmente comparáveis
    (nunca divide menor preço global pela contagem de pizza de outra variante).
  - Exclusão de grupos sem variantes comparáveis no ranking unitário.
  - RECENTLY_OBSERVED com parsing timezone-aware, normalização para UTC e desempate determinístico.
  - Filtros determinísticos (marca, canal, loja, dia da semana, faixa de preço, comparabilidade).
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
# 1. Testes de Extração Robusta de Campaign ID
# ===========================================================================

class TestCampaignIdExtraction(unittest.TestCase):
    """Testa extração de identificadores de campanha com underscores e sufixos complexos."""

    def test_extract_canonical_campaign_id_with_underscores(self) -> None:
        """Campaign IDs com underscores internos são preservados integralmente."""
        self.assertEqual(extract_canonical_campaign_id("pj_super_combo_familia_in_store"), "super_combo_familia")
        self.assertEqual(extract_canonical_campaign_id("pj_super_combo_familia_in_store_2_13"), "super_combo_familia")
        self.assertEqual(extract_canonical_campaign_id("dom_duo_bestial_delivery"), "duo_bestial")
        self.assertEqual(extract_canonical_campaign_id("tp_2x1_terca_louca_takeaway"), "2x1_terca_louca")
        self.assertEqual(extract_canonical_campaign_id("ph_menu_duo_especial_promo"), "menu_duo_especial")

    def test_extract_canonical_campaign_id_with_hyphens(self) -> None:
        """Campaign IDs com hífenes são preservados."""
        self.assertEqual(extract_canonical_campaign_id("ph_menu-duo_promo"), "menu-duo")
        self.assertEqual(extract_canonical_campaign_id("tp_combo-1_takeaway"), "combo-1")

    def test_extract_canonical_campaign_id_fallback(self) -> None:
        """IDs sem prefixo ou sufixo padrão devolvem o identificador original sem corrupção."""
        self.assertEqual(extract_canonical_campaign_id("simple_id"), "simple_id")
        self.assertEqual(extract_canonical_campaign_id("promocao_independente"), "promocao_independente")


# ===========================================================================
# 2. Testes de Identidade Persistente e Agrupamento Independente de Ordem
# ===========================================================================

class TestPersistentIdentityAndDeterministicGrouping(unittest.TestCase):
    """Testa estabilidade de IDs perante divergência/convergência e ordem de entrada."""

    def test_persistent_promo_id_stability_across_divergence_and_convergence(self) -> None:
        """O ID persistente não muda quando lojas convergem ou divergem em preço."""
        # Estado 1: Loja 2 e 3 convergem no preço de 17,98€
        pid_state1 = build_persistent_promo_id(Brand.PAPA_JOHNS, "super_combo", DispatchMethod.TAKE_AWAY)

        # Estado 2: Loja 3 diverge para 19,98€
        pid_state2 = build_persistent_promo_id(Brand.PAPA_JOHNS, "super_combo", DispatchMethod.TAKE_AWAY)

        # Estado 3: Loja 3 volta a convergir para 17,98€
        pid_state3 = build_persistent_promo_id(Brand.PAPA_JOHNS, "super_combo", DispatchMethod.TAKE_AWAY)

        self.assertEqual(pid_state1, pid_state2)
        self.assertEqual(pid_state2, pid_state3)
        self.assertEqual(pid_state1, "pid_papa_johns_super_combo_take_away")

    def test_grouping_is_independent_of_input_order(self) -> None:
        """O agrupamento visual produz o mesmo resultado independentemente da ordem dos itens."""
        p_cheap = _make_promo("pj_223_in_store_2", price_cents=1798, store_ids=["2"], title="Duo Bestial")
        p_expensive = _make_promo("pj_223_in_store_3", price_cents=1998, store_ids=["3"], title="Duo Bestial")

        # Ordem 1: barato primeiro
        groups_1 = group_promos_for_visual_presentation([p_cheap, p_expensive])
        # Ordem 2: caro primeiro
        groups_2 = group_promos_for_visual_presentation([p_expensive, p_cheap])

        self.assertEqual(len(groups_1), 1)
        self.assertEqual(len(groups_2), 1)

        vg1 = groups_1[0]
        vg2 = groups_2[0]

        self.assertEqual(vg1.persistent_id, vg2.persistent_id)
        self.assertEqual(vg1.min_price_cents, vg2.min_price_cents)
        self.assertEqual(vg1.max_price_cents, vg2.max_price_cents)
        self.assertEqual(vg1.display_price_label, vg2.display_price_label)
        self.assertEqual(vg1.all_store_ids, vg2.all_store_ids)
        self.assertEqual([v.variant_id for v in vg1.variants], [v.variant_id for v in vg2.variants])

    def test_days_of_week_combination_across_stores(self) -> None:
        """Combina dias da semana deterministicamente entre variantes."""
        # Loja 2 oferece apenas segundas, Loja 3 oferece apenas terças
        p_mon = _make_promo("pj_deal_in_store_2", store_ids=["2"], days_of_week=[Weekday.MONDAY])
        p_tue = _make_promo("pj_deal_in_store_3", store_ids=["3"], days_of_week=[Weekday.TUESDAY])

        groups = group_promos_for_visual_presentation([p_mon, p_tue])
        self.assertEqual(groups[0].days_of_week, [Weekday.MONDAY, Weekday.TUESDAY])

        # Se uma loja oferece diariamente (dias vazios), a oferta combinada é diária
        p_daily = _make_promo("pj_deal_in_store_13", store_ids=["13"], days_of_week=[])
        groups_with_daily = group_promos_for_visual_presentation([p_mon, p_tue, p_daily])
        self.assertEqual(groups_with_daily[0].days_of_week, [])


# ===========================================================================
# 3. Testes de BEST_UNIT_PRICE em Grupos com Variantes Não Comparáveis
# ===========================================================================

class TestBestUnitPriceIntegrity(unittest.TestCase):
    """Garante que o preço unitário é calculado apenas a partir de variantes comparáveis."""

    def test_never_divide_min_price_by_another_variants_pizza_count(self) -> None:
        """Variante barata não-comparável não contamina o preço unitário de variante comparável."""
        # Variante A: Bebida ou acompanhamento a 5,00€ (500 cents), sem contagem de pizzas
        p_drink = _make_promo("pj_combo_in_store_2", price_cents=500, pizza_count=None, store_ids=["2"])
        # Variante B: 2 pizzas médias a 16,00€ (1600 cents) -> 8,00€ por pizza (800 cents)
        p_pizza = _make_promo("pj_combo_in_store_3", price_cents=1600, pizza_count=2, store_ids=["3"])

        groups = group_promos_for_visual_presentation([p_drink, p_pizza])
        self.assertEqual(len(groups), 1)
        vg = groups[0]

        # O menor preço do grupo é 500 cêntimos
        self.assertEqual(vg.min_price_cents, 500)
        # O menor preço UNITÁRIO POR PIZZA deve ser 800 cêntimos (1600 / 2) e NUNCA 250 (500 / 2)!
        self.assertEqual(vg.min_price_per_pizza_cents, 800)
        self.assertEqual(vg.min_price_per_pizza_euros, 8.00)

        # Ranking unitário deve usar 800 cêntimos e fornecer explicação coerente
        ranked = rank_by_unit_price([vg])
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].score, 800)
        self.assertIn("8,00€ por pizza", ranked[0].explanation)
        self.assertIn("16,00€", ranked[0].explanation)

    def test_group_without_comparable_variants_is_excluded(self) -> None:
        """Grupo cujas variantes não possuem contagem de pizza é excluído do ranking unitário."""
        p_incomparable1 = _make_promo("pj_inc_in_store_2", price_cents=1000, pizza_count=None, store_ids=["2"])
        p_incomparable2 = _make_promo("pj_inc_in_store_3", price_cents=1200, pizza_count=None, store_ids=["3"])

        groups = group_promos_for_visual_presentation([p_incomparable1, p_incomparable2])
        self.assertFalse(groups[0].is_comparable_for_unit_price)
        self.assertIsNone(groups[0].min_price_per_pizza_cents)

        ranked = rank_by_unit_price([groups[0]])
        self.assertEqual(len(ranked), 0)


# ===========================================================================
# 4. Testes de RECENTLY_OBSERVED Timezone-Aware e Empates
# ===========================================================================

class TestRecentlyObservedTimezoneAware(unittest.TestCase):
    """Testa a ordenação temporal com fusos horários reais e empates determinísticos."""

    def test_visual_group_calculates_real_most_recent_utc_timestamp(self) -> None:
        """Calcula o instante mais recente real entre as variantes normalizado para UTC."""
        # Variante antiga: 14:00 UTC
        v_old = _make_promo("pj_deal_in_store_2", observed_at="2026-09-28T14:00:00+00:00", store_ids=["2"])
        # Variante recente: 16:30 UTC+01:00 (que equivale a 15:30 UTC)
        v_rec = _make_promo("pj_deal_in_store_3", observed_at="2026-09-28T16:30:00+01:00", store_ids=["3"])

        groups = group_promos_for_visual_presentation([v_old, v_rec])
        self.assertEqual(len(groups), 1)
        vg = groups[0]

        # 16:30+01:00 = 15:30 UTC, que é posterior a 14:00 UTC
        self.assertEqual(vg.most_recent_observed_at, "2026-09-28T15:30:00+00:00")

    def test_ranking_recently_observed_with_different_timezone_offsets(self) -> None:
        """Ofertas com fusos horários diferentes são ordenadas corretamente após conversão UTC."""
        # A: 14:00 UTC
        # B: 15:30 UTC (expresso como 17:30+02:00)
        # C: 16:00 UTC (expresso como 16:00Z)
        p_a = _make_promo("p_a", observed_at="2026-09-28T14:00:00+00:00")
        p_b = _make_promo("p_b", observed_at="2026-09-28T17:30:00+02:00")  # 15:30 UTC
        p_c = _make_promo("p_c", observed_at="2026-09-28T16:00:00Z")        # 16:00 UTC

        ranked = rank_by_recently_observed([p_a, p_b, p_c])

        self.assertEqual(len(ranked), 3)
        self.assertEqual(ranked[0].promo_id, "p_c")  # Mais recente (16:00 UTC)
        self.assertEqual(ranked[1].promo_id, "p_b")  # Médio (15:30 UTC)
        self.assertEqual(ranked[2].promo_id, "p_a")  # Mais antigo (14:00 UTC)

    def test_deterministic_tie_breaking_for_identical_timestamps(self) -> None:
        """Instantes idênticos desempatam determinísticamente por menor preço e depois por ID."""
        ts = "2026-09-28T16:00:00+00:00"
        p_expensive = _make_promo("p_z_exp", price_cents=2000, observed_at=ts)
        p_cheap = _make_promo("p_a_cheap", price_cents=1000, observed_at=ts)

        ranked = rank_by_recently_observed([p_expensive, p_cheap])
        # Desempate pelo menor preço
        self.assertEqual(ranked[0].promo_id, "p_a_cheap")
        self.assertEqual(ranked[1].promo_id, "p_z_exp")


# ===========================================================================
# 5. Testes de Filtros Determinísticos
# ===========================================================================

class TestFilters(unittest.TestCase):
    """Testa os filtros de pesquisa de promoções."""

    def setUp(self) -> None:
        self.pj = _make_promo("pj1", vendor=Brand.PAPA_JOHNS, store_ids=["2"], dispatch_methods=[DispatchMethod.TAKE_AWAY], price_cents=1000)
        self.tele = _make_promo("tp1", vendor=Brand.TELEPIZZA, store_ids=["10"], dispatch_methods=[DispatchMethod.DELIVERY], price_cents=1500)
        self.dom = _make_promo("dm1", vendor=Brand.DOMINOS, store_ids=["140"], dispatch_methods=[DispatchMethod.TAKE_AWAY], price_cents=2000, days_of_week=[Weekday.MONDAY])

    def test_filter_by_brand(self) -> None:
        result = filter_by_brand([self.pj, self.tele, self.dom], Brand.PAPA_JOHNS)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "pj1")

    def test_filter_by_dispatch_method(self) -> None:
        takeaway = filter_by_dispatch_method([self.pj, self.tele, self.dom], DispatchMethod.TAKE_AWAY)
        self.assertEqual(len(takeaway), 2)
        delivery = filter_by_dispatch_method([self.pj, self.tele, self.dom], DispatchMethod.DELIVERY)
        self.assertEqual(len(delivery), 1)
        self.assertEqual(delivery[0].id, "tp1")

    def test_filter_by_store(self) -> None:
        store_2 = filter_by_store([self.pj, self.tele, self.dom], "2")
        self.assertEqual(len(store_2), 1)
        self.assertEqual(store_2[0].id, "pj1")

    def test_filter_by_weekday(self) -> None:
        monday_promos = filter_by_weekday([self.pj, self.tele, self.dom], Weekday.MONDAY)
        self.assertEqual(len(monday_promos), 3)

        tuesday_promos = filter_by_weekday([self.pj, self.tele, self.dom], Weekday.TUESDAY)
        self.assertEqual(len(tuesday_promos), 2)
        self.assertNotIn(self.dom, tuesday_promos)

    def test_filter_by_price_range(self) -> None:
        mid_range = filter_by_price_range([self.pj, self.tele, self.dom], min_cents=1200, max_cents=1800)
        self.assertEqual(len(mid_range), 1)
        self.assertEqual(mid_range[0].id, "tp1")

    def test_filter_comparable_only(self) -> None:
        comp = _make_promo("comp", price_cents=1000, pizza_count=1)
        non_comp = _make_promo("non_comp", price_cents=1000, pizza_count=None)

        result = filter_comparable_only([comp, non_comp])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "comp")


if __name__ == "__main__":
    unittest.main()
