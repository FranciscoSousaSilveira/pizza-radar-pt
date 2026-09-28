"""Testes unitários dos modelos canónicos (UnifiedPromo e Enums)."""

import json
import unittest

from pizza_radar.core.models import (
    Brand,
    DispatchMethod,
    DiscountType,
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
        )
        self.assertEqual(promo.id, "pj-1")
        self.assertEqual(promo.vendor, Brand.PAPA_JOHNS)
        self.assertEqual(promo.title, "Menu 2x1 Terça-feira")
        self.assertEqual(promo.location_scope, "Lisboa")
        self.assertEqual(promo.target_audience, TargetAudience.ALL)
        self.assertEqual(
            promo.dispatch_methods,
            [DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY],
        )

    def test_string_conversion_to_enums_in_post_init(self) -> None:
        """Verifica se strings são automaticamente convertidas para os enums tipados."""
        promo = UnifiedPromo(
            id="tp-1",
            vendor="TELEPIZZA",  # type: ignore[arg-type]
            title="Terça Louca",
            description="Pizzas a metade do preço.",
            discount_type="PERCENTAGE",  # type: ignore[arg-type]
            target_audience="GROUP_FAMILY",  # type: ignore[arg-type]
            days_of_week=["TUESDAY"],  # type: ignore[list-item]
            dispatch_methods=["DELIVERY"],  # type: ignore[list-item]
        )
        self.assertIsInstance(promo.vendor, Brand)
        self.assertEqual(promo.vendor, Brand.TELEPIZZA)
        self.assertIsInstance(promo.discount_type, DiscountType)
        self.assertEqual(promo.discount_type, DiscountType.PERCENTAGE)
        self.assertIsInstance(promo.target_audience, TargetAudience)
        self.assertEqual(promo.target_audience, TargetAudience.GROUP_FAMILY)
        self.assertIsInstance(promo.days_of_week[0], Weekday)
        self.assertEqual(promo.days_of_week[0], Weekday.TUESDAY)
        self.assertIsInstance(promo.dispatch_methods[0], DispatchMethod)
        self.assertEqual(promo.dispatch_methods[0], DispatchMethod.DELIVERY)

    def test_savings_and_discount_calculation(self) -> None:
        """Valida os cálculos de poupança nominal e percentual de desconto."""
        promo = UnifiedPromo(
            id="ph-1",
            vendor=Brand.PIZZA_HUT,
            title="Menu Familiar",
            description="1 Pizza Familiar + 4 Pães de Alho",
            price=24.25,
            original_price=34.25,
        )
        self.assertEqual(promo.savings_amount, 10.00)
        # 10 / 34.25 = 29.197% -> 29.2%
        self.assertEqual(promo.computed_discount_percentage, 29.2)

    def test_savings_with_missing_prices(self) -> None:
        """Valida cálculos quando os preços não são ambos fornecidos."""
        promo = UnifiedPromo(
            id="d-1",
            vendor=Brand.DOMINOS,
            title="Promo Especial",
            description="Preço fixo sem preço original conhecido",
            price=9.95,
            original_price=None,
        )
        self.assertIsNone(promo.savings_amount)
        self.assertIsNone(promo.computed_discount_percentage)

    def test_explicit_discount_percentage_overrides_computed(self) -> None:
        """Verifica se uma percentagem explicitamente definida prevalece."""
        promo = UnifiedPromo(
            id="d-2",
            vendor=Brand.DOMINOS,
            title="Desconto 50%",
            description="50% em pizzas médias",
            price=10.00,
            original_price=20.00,
            discount_percentage=50.0,
        )
        self.assertEqual(promo.computed_discount_percentage, 50.0)

    def test_serialization_to_dict_and_from_dict(self) -> None:
        """Valida serialização e desserialização completa de e para dicionário."""
        original = UnifiedPromo(
            id="pj-full",
            vendor=Brand.PAPA_JOHNS,
            title="Combo Especial",
            description="Pizza + Bebida",
            price=12.50,
            original_price=18.00,
            discount_percentage=30.6,
            discount_type=DiscountType.SPECIAL_MENU,
            conditions="Válido apenas às quintas-feiras.",
            valid_from="2026-09-01T00:00:00",
            valid_until="2026-12-31T23:59:59",
            days_of_week=[Weekday.THURSDAY],
            dispatch_methods=[DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY],
            target_audience=TargetAudience.INDIVIDUAL,
            image_url="https://papajohns.pt/img/combo.png",
            source_url="https://papajohns.pt/promocoes",
            scraped_at="2026-09-28T16:00:00",
            location_scope="Lisboa",
        )

        data = original.to_dict()
        self.assertIsInstance(data["vendor"], str)
        self.assertEqual(data["vendor"], "PAPA_JOHNS")
        self.assertEqual(data["days_of_week"], ["THURSDAY"])

        restored = UnifiedPromo.from_dict(data)
        self.assertEqual(original.id, restored.id)
        self.assertEqual(original.vendor, restored.vendor)
        self.assertEqual(original.title, restored.title)
        self.assertEqual(original.price, restored.price)
        self.assertEqual(original.days_of_week, restored.days_of_week)
        self.assertEqual(original.dispatch_methods, restored.dispatch_methods)

    def test_json_roundtrip(self) -> None:
        """Valida que a serialização JSON e desserialização preservam os dados."""
        original = UnifiedPromo(
            id="test-json",
            vendor=Brand.DOMINOS,
            title="Oferta Teste",
            description="Descrição teste",
            price=8.95,
        )
        json_str = original.to_json()
        restored = UnifiedPromo.from_json(json_str)
        self.assertEqual(original.id, restored.id)
        self.assertEqual(original.vendor, restored.vendor)
        self.assertEqual(original.price, restored.price)


if __name__ == "__main__":
    unittest.main()
