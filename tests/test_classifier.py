"""Testes unitários determinísticos para classificação de tipo de oferta (Issue #25).

Invariantes de Engenharia:
1. Zero IA em runtime (100% determinístico e previsível).
2. Itens não-pizza (refrigerantes, gelados, sobremesas, pão de alho) classificados como NON_PIZZA.
3. Pizzas com complementos classificadas como BUNDLE_WITH_PIZZA.
4. Pizzas isoladas ou combinadas classificadas como PIZZA.
5. Inconclusivo ou não comprovado classificado como UNKNOWN.
"""

from __future__ import annotations

import unittest

from pizza_radar.core.classifier import classify_offer_type
from pizza_radar.core.models import (
    ComponentCategory,
    OfferComponent,
    OfferType,
    PizzaSize,
    UnifiedPromo,
    Brand,
)
from pizza_radar.engine.identity import group_promos_for_visual_presentation
from pizza_radar.engine.rankings import rank_by_lowest_price, rank_by_unit_price


class TestOfferClassifier(unittest.TestCase):
    """Testa a função classify_offer_type e o isolamento de produtos."""

    def test_non_pizza_drinks_and_desserts(self) -> None:
        """Confirma que refrigerantes, gelados e sobremesas são categoricamente classificados como NON_PIZZA."""
        cases = [
            ("2 Refrigerantes 1.5L", "Coca-cola, Fanta ou Sprite à escolha"),
            ("Copo Gelado Ben & Jerry's", "Chocolate Fudge Brownie 465ml"),
            ("Pão de Alho Supremo", "Pão de alho crocante com queijo mozarela"),
            ("Asas de Frango Barbecue", "6 unidades com molho barbecue"),
            ("Batatas Rústicas", "Porção individual com molho de alho"),
            ("Cookie Chocolate", "Cookie artesanal com pepitas"),
        ]
        for title, desc in cases:
            with self.subTest(title=title):
                res = classify_offer_type(title=title, description=desc)
                self.assertEqual(
                    res,
                    OfferType.NON_PIZZA,
                    f"'{title}' deveria ser NON_PIZZA mas foi {res}",
                )

    def test_bundle_with_pizza(self) -> None:
        """Confirma que menus com pizza + bebida/acompanhamento são classificados como BUNDLE_WITH_PIZZA."""
        cases = [
            ("Menu Individual Pizza + Bebida", "1 Pizza Média e 1 Refrigerante de lata"),
            ("Pack Família 2 Pizzas + Gelado", "2 Pizzas Grandes e 1 copo Ben & Jerry's"),
            ("Combo Pizza + Pão de Alho", "Pizza média clássica com pão de alho"),
        ]
        for title, desc in cases:
            with self.subTest(title=title):
                res = classify_offer_type(title=title, description=desc)
                self.assertEqual(
                    res,
                    OfferType.BUNDLE_WITH_PIZZA,
                    f"'{title}' deveria ser BUNDLE_WITH_PIZZA mas foi {res}",
                )

    def test_pure_pizza(self) -> None:
        """Confirma que ofertas de pizza pura são classificadas como PIZZA."""
        cases = [
            ("Pizza Média 3 Ingredientes", "Massa fina com mozarela e 3 ingredientes"),
            ("2 Pizzas Grandes Pan", "2 pizzas grandes massa pan clássica"),
            ("Calzone Especial", "Calzone recheado com queijo e fiambre"),
        ]
        for title, desc in cases:
            with self.subTest(title=title):
                res = classify_offer_type(title=title, description=desc)
                self.assertEqual(
                    res,
                    OfferType.PIZZA,
                    f"'{title}' deveria ser PIZZA mas foi {res}",
                )

    def test_explicit_pizza_count_overrides_unknown(self) -> None:
        """Se pizza_count for informado explicitamente (> 0), a oferta é reconhecida como pizza."""
        res = classify_offer_type(title="Oferta Especial", description="Preço de amigo", pizza_count=2)
        self.assertEqual(res, OfferType.PIZZA)

    def test_unknown_when_unproven(self) -> None:
        """Termos genéricos sem prova de produto mantêm-se como UNKNOWN."""
        cases = [
            ("Segundas a Dobrar", "Pede 1 e leva 2"),
            ("Super Desconto 50%", "Desconto imediato em toda a carta"),
        ]
        for title, desc in cases:
            with self.subTest(title=title):
                res = classify_offer_type(title=title, description=desc)
                self.assertEqual(res, OfferType.UNKNOWN)

    def test_structured_included_items_precedence(self) -> None:
        """A presença de included_items estruturados tem precedência sobre texto."""
        # Apenas pizza
        res_pizza = classify_offer_type(
            title="Promoção",
            included_items=[OfferComponent(category=ComponentCategory.PIZZA, quantity=1)],
        )
        self.assertEqual(res_pizza, OfferType.PIZZA)

        # Pizza + Drink
        res_bundle = classify_offer_type(
            title="Promoção",
            included_items=[
                OfferComponent(category=ComponentCategory.PIZZA, quantity=1),
                OfferComponent(category=ComponentCategory.DRINK, quantity=2),
            ],
        )
        self.assertEqual(res_bundle, OfferType.BUNDLE_WITH_PIZZA)

        # Apenas Drink
        res_drink = classify_offer_type(
            title="Promoção",
            included_items=[OfferComponent(category=ComponentCategory.DRINK, quantity=2)],
        )
        self.assertEqual(res_drink, OfferType.NON_PIZZA)


class TestPizzaOnlyMetricsIsolation(unittest.TestCase):
    """Testa o isolamento de métricas para impedir que complementos determinem rankings de pizza."""

    def test_non_pizza_excluded_from_best_unit_price(self) -> None:
        """Itens NON_PIZZA e UNKNOWN nunca entram no ranking BEST_UNIT_PRICE."""
        # Refrigerante a 2.99€ (299 cents)
        p_drink = UnifiedPromo(
            id="pj_drink",
            vendor=Brand.PAPA_JOHNS,
            title="2 Refrigerantes 1.5L",
            description="Coca-cola",
            observed_at="2026-09-29T12:00:00+00:00",
            price_cents=299,
            offer_type=OfferType.NON_PIZZA,
        )

        # Pizza a 11.99€ (1199 cents, 1 pizza)
        p_pizza = UnifiedPromo(
            id="pj_pizza",
            vendor=Brand.PAPA_JOHNS,
            title="Pizza Média Clássica",
            description="1 Pizza média",
            observed_at="2026-09-29T12:00:00+00:00",
            price_cents=1199,
            pizza_count=1,
            pizza_size=PizzaSize.MEDIUM,
            offer_type=OfferType.PIZZA,
        )

        groups = group_promos_for_visual_presentation([p_drink, p_pizza])
        self.assertEqual(len(groups), 2)

        # Ranking de preço unitário por pizza
        ranked = rank_by_unit_price(groups)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].item.vendor, Brand.PAPA_JOHNS)
        self.assertIn("Pizza Média", ranked[0].item.title)
        self.assertEqual(ranked[0].score, 1199)

    def test_lowest_price_ranking_with_pizza_only_toggle(self) -> None:
        """LOWEST_ABSOLUTE_PRICE com pizza_only=True filtra ofertas não-pizza."""
        p_drink = UnifiedPromo(
            id="pj_drink",
            vendor=Brand.PAPA_JOHNS,
            title="Copo Gelado Ben & Jerry's",
            description="Gelado 465ml",
            observed_at="2026-09-29T12:00:00+00:00",
            price_cents=649,
            offer_type=OfferType.NON_PIZZA,
        )
        p_pizza = UnifiedPromo(
            id="pj_pizza",
            vendor=Brand.PAPA_JOHNS,
            title="Pizza Média",
            description="Massa tradicional",
            observed_at="2026-09-29T12:00:00+00:00",
            price_cents=999,
            pizza_count=1,
            offer_type=OfferType.PIZZA,
        )

        groups = group_promos_for_visual_presentation([p_drink, p_pizza])

        # Sem filtro de pizza: gelado a 6.49€ fica em #1
        ranked_all = rank_by_lowest_price(groups, pizza_only=False)
        self.assertEqual(len(ranked_all), 2)
        self.assertEqual(ranked_all[0].score, 649)

        # Com pizza_only=True: apenas a pizza a 9.99€ é elegível
        ranked_pizza = rank_by_lowest_price(groups, pizza_only=True)
        self.assertEqual(len(ranked_pizza), 1)
        self.assertEqual(ranked_pizza[0].score, 999)
        self.assertIn("Pizza", ranked_pizza[0].item.title)


if __name__ == "__main__":
    unittest.main()
