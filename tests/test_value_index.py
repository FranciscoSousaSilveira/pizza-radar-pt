"""Testes unitários determinísticos do Pizza Value Index (Custo / Benefício)."""

import math
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from pizza_radar.core.models import (
    Brand,
    DispatchMethod,
    OfferType,
    PizzaSize,
    StoreScope,
    UnifiedPromo,
)
from pizza_radar.engine.identity import StoreVariant, VisualPromoGroup
from pizza_radar.engine.rankings import (
    RankingCriteria,
    rank_by_value_index,
)
from pizza_radar.engine.value_index import (
    CM2_PER_PORTION,
    DIAMETER_BY_SIZE_CM,
    calculate_pizza_area_cm2,
    compute_value_metrics,
    estimate_portions,
)


class TestValueIndex(unittest.TestCase):
    """Garante a precisão matemática e comportamento determinístico do Value Index."""

    def test_diameter_and_area_formulas(self):
        """Verifica os diâmetros padrão e o cálculo exato da área em cm²."""
        self.assertEqual(DIAMETER_BY_SIZE_CM[PizzaSize.INDIVIDUAL], 20.0)
        self.assertEqual(DIAMETER_BY_SIZE_CM[PizzaSize.MEDIUM], 30.0)
        self.assertEqual(DIAMETER_BY_SIZE_CM[PizzaSize.LARGE], 35.0)
        self.assertEqual(DIAMETER_BY_SIZE_CM[PizzaSize.FAMILY], 38.0)

        # Individual 20cm: pi * 10^2 = 100 * pi ~ 314.159 cm²
        area_ind = calculate_pizza_area_cm2(PizzaSize.INDIVIDUAL, count=1)
        self.assertAlmostEqual(area_ind, 100.0 * math.pi, places=2)

        # Média 30cm com 2 pizzas: 2 * pi * 15^2 = 2 * 225 * pi ~ 1413.72 cm²
        area_med_2 = calculate_pizza_area_cm2(PizzaSize.MEDIUM, count=2)
        self.assertAlmostEqual(area_med_2, 450.0 * math.pi, places=2)

        # Pizza com tamanho desconhecido ou contagem nula deve retornar 0.0
        self.assertEqual(calculate_pizza_area_cm2(PizzaSize.UNKNOWN), 0.0)
        self.assertEqual(calculate_pizza_area_cm2(PizzaSize.MEDIUM, count=0), 0.0)

    def test_estimate_portions(self):
        """Verifica a estimativa de doses/pessoas (~450 cm² por pessoa)."""
        # 1 Individual (314 cm²): 1 pessoa
        self.assertEqual(estimate_portions(calculate_pizza_area_cm2(PizzaSize.INDIVIDUAL, 1)), 1)
        # 1 Média (706.8 cm²): round(706.8 / 450) = 2 pessoas
        self.assertEqual(estimate_portions(calculate_pizza_area_cm2(PizzaSize.MEDIUM, 1)), 2)
        # 1 Familiar (1134 cm²): round(1134 / 450) = 3 pessoas
        self.assertEqual(estimate_portions(calculate_pizza_area_cm2(PizzaSize.FAMILY, 1)), 3)
        # 2 Médias (1414 cm²): round(1414 / 450) = 3 pessoas
        self.assertEqual(estimate_portions(calculate_pizza_area_cm2(PizzaSize.MEDIUM, 2)), 3)

    def test_compute_value_metrics_medium_pizza(self):
        """Calcula métricas de valor para uma pizza Média a 8,95€."""
        # Preço: 895 cêntimos. Área: pi * 15^2 = 706.858 cm²
        # Preço por 100 cm²: 895 / (706.858 / 100) = 895 / 7.06858 = 126.6 cêntimos (1,27€)
        metrics = compute_value_metrics(price_cents=895, pizza_size=PizzaSize.MEDIUM, pizza_count=1)
        self.assertIsNotNone(metrics)
        self.assertAlmostEqual(metrics.total_area_cm2, math.pi * 225, places=2)
        self.assertEqual(metrics.price_per_100_cm2_cents, 127)
        self.assertEqual(metrics.price_per_100_cm2_euros, 1.27)
        self.assertEqual(metrics.estimated_portions, 2)
        self.assertEqual(metrics.value_badge_label, "1,27 € / 100 cm²")
        self.assertEqual(metrics.portion_badge_label, "Ideal para 2 pessoas")

    def test_compute_value_metrics_unknown_size_returns_none(self):
        """Ofertas sem tamanho ou preço não inventam área e retornam None."""
        self.assertIsNone(compute_value_metrics(price_cents=999, pizza_size=PizzaSize.UNKNOWN))
        self.assertIsNone(compute_value_metrics(price_cents=None, pizza_size=PizzaSize.MEDIUM))
        self.assertIsNone(compute_value_metrics(price_cents=0, pizza_size=PizzaSize.MEDIUM))

    def test_rank_by_value_index_deterministic(self):
        """Verifica a ordenação pelo Value Index com menor custo por cm² em primeiro."""
        now = datetime.now(timezone.utc)

        # Oferta A: Média a 12,00€ (Área 706.8 cm² -> 1200 / 7.068 = ~170 cêntimos / 100 cm²)
        var_a = StoreVariant(
            variant_id="var_a",
            persistent_id="promo_a",
            price_cents=1200,
            pizza_size=PizzaSize.MEDIUM,
            pizza_count=1,
            offer_type=OfferType.PIZZA,
        )
        group_a = VisualPromoGroup(
            persistent_id="promo_a",
            vendor=Brand.DOMINOS,
            title="Média Regular",
            description="",
            dispatch_methods=[DispatchMethod.DELIVERY],
            store_scope=StoreScope.NATIONAL,
            variants=[var_a],
            pizza_size=PizzaSize.MEDIUM,
            pizza_count=1,
            offer_type=OfferType.PIZZA,
        )

        # Oferta B: 2 Familiares a 20,00€ (Área 2 * 1134 cm² = 2268 cm² -> 2000 / 22.68 = ~88 cêntimos / 100 cm²)
        var_b = StoreVariant(
            variant_id="var_b",
            persistent_id="promo_b",
            price_cents=2000,
            pizza_size=PizzaSize.FAMILY,
            pizza_count=2,
            offer_type=OfferType.PIZZA,
        )
        group_b = VisualPromoGroup(
            persistent_id="promo_b",
            vendor=Brand.TELEPIZZA,
            title="2 Familiares Super Preço",
            description="",
            dispatch_methods=[DispatchMethod.TAKE_AWAY],
            store_scope=StoreScope.NATIONAL,
            variants=[var_b],
            pizza_size=PizzaSize.FAMILY,
            pizza_count=2,
            offer_type=OfferType.PIZZA,
        )

        # Oferta C: Sem tamanho conhecido (deve ser excluída do ranking de valor)
        var_c = StoreVariant(
            variant_id="var_c",
            persistent_id="promo_c",
            price_cents=999,
            pizza_size=PizzaSize.UNKNOWN,
            pizza_count=1,
            offer_type=OfferType.PIZZA,
        )
        group_c = VisualPromoGroup(
            persistent_id="promo_c",
            vendor=Brand.PIZZA_HUT,
            title="Oferta Sem Tamanho",
            description="",
            dispatch_methods=[DispatchMethod.DELIVERY],
            store_scope=StoreScope.NATIONAL,
            variants=[var_c],
            pizza_size=PizzaSize.UNKNOWN,
            offer_type=OfferType.PIZZA,
        )

        ranked = rank_by_value_index([group_a, group_b, group_c])

        # Oferta B deve ficar em 1º lugar (88 cêntimos < 170 cêntimos)
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0].item.persistent_id, "promo_b")
        self.assertEqual(ranked[0].criteria, RankingCriteria.BEST_VALUE_INDEX)
        self.assertEqual(ranked[1].item.persistent_id, "promo_a")
        self.assertEqual(ranked[1].criteria, RankingCriteria.BEST_VALUE_INDEX)
        self.assertLess(ranked[0].score, ranked[1].score)


if __name__ == "__main__":
    unittest.main()
