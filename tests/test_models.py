"""Testes unitários dos modelos canónicos (UnifiedPromo, OfferComponent e Enums)."""

import json
import unittest

from pizza_radar.core.models import (
    Brand,
    ComponentCategory,
    DispatchMethod,
    DiscountType,
    OfferComponent,
    PizzaSize,
    StoreScope,
    TargetAudience,
    UnifiedPromo,
    Weekday,
)


class TestUnifiedPromoModels(unittest.TestCase):
    """Bateria de testes para o modelo canónico UnifiedPromo."""

    def test_minimal_instantiation(self) -> None:
        """Verifica a instanciação com apenas os campos obrigatórios."""
        promo = UnifiedPromo(
            id="pj-1",
            vendor=Brand.PAPA_JOHNS,
            title="Menu 2x1 Terça-feira",
            description="Duas pizzas médias pelo preço de uma.",
            observed_at="2026-09-28T16:00:00+01:00",
        )
        self.assertEqual(promo.id, "pj-1")
        self.assertEqual(promo.vendor, Brand.PAPA_JOHNS)
        self.assertEqual(promo.title, "Menu 2x1 Terça-feira")
        self.assertEqual(promo.observed_at, "2026-09-28T16:00:00+01:00")
        self.assertEqual(promo.location_scope, "Lisboa")
        self.assertEqual(promo.store_scope, StoreScope.UNKNOWN)
        self.assertEqual(promo.target_audience, TargetAudience.ALL)
        self.assertEqual(
            promo.dispatch_methods,
            [DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY],
        )
        self.assertFalse(promo.is_comparable_for_unit_price)

    def test_string_conversion_to_enums_in_post_init(self) -> None:
        """Verifica se strings são automaticamente convertidas para os enums tipados."""
        promo = UnifiedPromo(
            id="tp-1",
            vendor="TELEPIZZA",  # type: ignore[arg-type]
            title="Terça Louca",
            description="Pizzas a metade do preço.",
            observed_at="2026-09-28T16:00:00Z",
            discount_type="PERCENTAGE",  # type: ignore[arg-type]
            target_audience="GROUP_FAMILY",  # type: ignore[arg-type]
            store_scope="NATIONAL",  # type: ignore[arg-type]
            pizza_size="MEDIUM",  # type: ignore[arg-type]
            days_of_week=["TUESDAY"],  # type: ignore[list-item]
            dispatch_methods=["DELIVERY"],  # type: ignore[list-item]
        )
        self.assertIsInstance(promo.vendor, Brand)
        self.assertEqual(promo.vendor, Brand.TELEPIZZA)
        self.assertIsInstance(promo.discount_type, DiscountType)
        self.assertEqual(promo.discount_type, DiscountType.PERCENTAGE)
        self.assertIsInstance(promo.target_audience, TargetAudience)
        self.assertEqual(promo.target_audience, TargetAudience.GROUP_FAMILY)
        self.assertIsInstance(promo.store_scope, StoreScope)
        self.assertEqual(promo.store_scope, StoreScope.NATIONAL)
        self.assertIsInstance(promo.pizza_size, PizzaSize)
        self.assertEqual(promo.pizza_size, PizzaSize.MEDIUM)
        self.assertIsInstance(promo.days_of_week[0], Weekday)
        self.assertEqual(promo.days_of_week[0], Weekday.TUESDAY)
        self.assertIsInstance(promo.dispatch_methods[0], DispatchMethod)
        self.assertEqual(promo.dispatch_methods[0], DispatchMethod.DELIVERY)

    def test_deterministic_money_cents_and_euros(self) -> None:
        """Valida que preços em cêntimos são inteiros determinísticos e convertidos em euros."""
        promo = UnifiedPromo(
            id="ph-1",
            vendor=Brand.PIZZA_HUT,
            title="Menu Familiar",
            description="1 Pizza Familiar + 4 Pães de Alho",
            observed_at="2026-09-28T16:00:00+01:00",
            price_cents=2425,  # 24.25€
            original_price_cents=3425,  # 34.25€
        )
        self.assertEqual(promo.price_cents, 2425)
        self.assertEqual(promo.original_price_cents, 3425)
        self.assertEqual(promo.price_euros, 24.25)
        self.assertEqual(promo.original_price_euros, 34.25)
        self.assertEqual(promo.savings_amount_cents, 1000)
        self.assertEqual(promo.savings_amount_euros, 10.00)
        # 1000 / 3425 = 29.197% -> 29.2%
        self.assertEqual(promo.computed_discount_percentage, 29.2)

    def test_savings_with_missing_prices(self) -> None:
        """Valida cálculos quando apenas um preço está presente."""
        promo = UnifiedPromo(
            id="d-1",
            vendor=Brand.DOMINOS,
            title="Promo Especial",
            description="Preço fixo sem preço original conhecido",
            observed_at="2026-09-28T16:00:00+01:00",
            price_cents=995,
            original_price_cents=None,
        )
        self.assertIsNone(promo.savings_amount_cents)
        self.assertIsNone(promo.savings_amount_euros)
        self.assertIsNone(promo.computed_discount_percentage)

    def test_explicit_discount_percentage_overrides_computed(self) -> None:
        """Verifica se uma percentagem explicitamente definida pela marca prevalece."""
        promo = UnifiedPromo(
            id="d-2",
            vendor=Brand.DOMINOS,
            title="Desconto 50%",
            description="50% em pizzas médias",
            observed_at="2026-09-28T16:00:00+01:00",
            price_cents=1000,
            original_price_cents=2000,
            discount_percentage=50.0,
        )
        self.assertEqual(promo.computed_discount_percentage, 50.0)

    def test_geographic_applicability_and_store_eligibility(self) -> None:
        """Valida que o contrato distingue oferta nacional, lojas específicas e desconhecido."""
        # 1. Oferta Nacional
        promo_nat = UnifiedPromo(
            id="nat-1",
            vendor=Brand.DOMINOS,
            title="Nacional",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
            store_scope=StoreScope.NATIONAL,
        )
        self.assertTrue(promo_nat.is_store_eligible("140"))
        self.assertTrue(promo_nat.is_store_eligible("qualquer_loja"))

        # 2. Oferta de Lojas Específicas
        promo_stores = UnifiedPromo(
            id="spec-1",
            vendor=Brand.DOMINOS,
            title="Areeiro e Telheiras",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
            store_scope=StoreScope.SPECIFIC_STORES,
            store_ids=["140", "142"],
            store_names=["Areeiro", "Telheiras"],
        )
        self.assertTrue(promo_stores.is_store_eligible("140"))
        self.assertFalse(promo_stores.is_store_eligible("999"))

        # 3. Aplicabilidade Desconhecida (não deve presumir elegibilidade)
        promo_unk = UnifiedPromo(
            id="unk-1",
            vendor=Brand.TELEPIZZA,
            title="Desconhecido",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
            store_scope=StoreScope.UNKNOWN,
        )
        self.assertIsNone(promo_unk.is_store_eligible("140"))

    def test_offer_content_components_and_unit_price_comparability(self) -> None:
        """Valida a composição da oferta e as regras estritas de comparabilidade."""
        # Oferta com contagem de pizzas fornecida pela fonte
        promo_comparable = UnifiedPromo(
            id="pj-2x1",
            vendor=Brand.PAPA_JOHNS,
            title="2x1 Terça",
            description="2 pizzas médias por 16€",
            observed_at="2026-09-28T16:00:00+01:00",
            price_cents=1600,
            pizza_count=2,
            pizza_size=PizzaSize.MEDIUM,
            included_items=[
                OfferComponent(category=ComponentCategory.PIZZA, quantity=2, size=PizzaSize.MEDIUM)
            ],
        )
        self.assertTrue(promo_comparable.is_comparable_for_unit_price)
        self.assertEqual(promo_comparable.price_per_pizza_cents, 800)
        self.assertEqual(promo_comparable.price_per_pizza_euros, 8.00)

        # Oferta genérica onde a fonte NÃO especificou quantidade de pizzas (não inventa valores)
        promo_incomparable = UnifiedPromo(
            id="ph-combo",
            vendor=Brand.PIZZA_HUT,
            title="Combo Especial de Jantar",
            description="Menu completo com entradas e bebidas",
            observed_at="2026-09-28T16:00:00+01:00",
            price_cents=1990,
            pizza_count=None,  # Faltam dados na fonte: nunca inventar!
        )
        self.assertFalse(promo_incomparable.is_comparable_for_unit_price)
        self.assertIsNone(promo_incomparable.price_per_pizza_cents)
        self.assertIsNone(promo_incomparable.price_per_pizza_euros)

    def test_serialization_roundtrip_dict_and_json(self) -> None:
        """Valida serialização e desserialização completa preservando todos os campos e enums."""
        original = UnifiedPromo(
            id="full-test-1",
            vendor=Brand.PAPA_JOHNS,
            title="Menu Duplo",
            description="Duas pizzas e bebidas",
            observed_at="2026-09-28T16:30:00+01:00",
            price_cents=1850,
            original_price_cents=2600,
            discount_percentage=28.8,
            discount_type=DiscountType.SPECIAL_MENU,
            conditions="Válido em Lisboa.",
            valid_from="2026-09-01T00:00:00+01:00",
            valid_until="2026-12-31T23:59:59+01:00",
            last_seen_at="2026-09-28T16:30:00+01:00",
            is_active=True,
            days_of_week=[Weekday.MONDAY, Weekday.WEDNESDAY],
            dispatch_methods=[DispatchMethod.DELIVERY],
            target_audience=TargetAudience.GROUP_FAMILY,
            store_scope=StoreScope.SPECIFIC_STORES,
            store_ids=["2"],
            store_names=["Amoreiras"],
            pizza_count=2,
            pizza_size=PizzaSize.MEDIUM,
            included_items=[
                OfferComponent(category=ComponentCategory.PIZZA, quantity=2, size=PizzaSize.MEDIUM),
                OfferComponent(category=ComponentCategory.DRINK, quantity=1, description="1.5L"),
            ],
            image_url="https://papajohns.pt/img/menu.jpg",
            source_url="https://papajohns.pt/promocoes",
            location_scope="Lisboa",
        )

        data = original.to_dict()
        self.assertEqual(data["price_cents"], 1850)
        self.assertEqual(data["vendor"], "PAPA_JOHNS")
        self.assertEqual(data["store_scope"], "SPECIFIC_STORES")
        self.assertEqual(len(data["included_items"]), 2)

        restored_from_dict = UnifiedPromo.from_dict(data)
        self.assertEqual(original.id, restored_from_dict.id)
        self.assertEqual(original.price_cents, restored_from_dict.price_cents)
        self.assertEqual(original.store_scope, restored_from_dict.store_scope)
        self.assertEqual(len(restored_from_dict.included_items), 2)
        self.assertEqual(restored_from_dict.included_items[0].category, ComponentCategory.PIZZA)

        json_str = original.to_json()
        restored_from_json = UnifiedPromo.from_json(json_str)
        self.assertEqual(original.id, restored_from_json.id)
        self.assertEqual(original.price_cents, restored_from_json.price_cents)
        self.assertEqual(original.pizza_count, restored_from_json.pizza_count)


if __name__ == "__main__":
    unittest.main()
