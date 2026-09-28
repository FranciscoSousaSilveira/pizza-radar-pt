"""Testes unitários para o validador canónico do UnifiedPromo."""

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
from pizza_radar.core.validator import (
    ValidationError,
    validate_promo,
    validate_promos,
)


class TestUnifiedPromoValidator(unittest.TestCase):
    """Testes exaustivos das regras de validação determinística."""

    def setUp(self) -> None:
        """Cria um objeto de promoção válido base para os testes."""
        self.valid_promo = UnifiedPromo(
            id="promo-valida-1",
            vendor=Brand.PAPA_JOHNS,
            title="Promoção de Teste Válida",
            description="Descrição válida para teste de esquema.",
            observed_at="2026-09-28T16:00:00+01:00",
            price_cents=1190,
            original_price_cents=1590,
            discount_percentage=25.2,
            discount_type=DiscountType.FIXED_PRICE,
            conditions="Válido de segunda a sexta no concelho de Lisboa.",
            valid_from="2026-09-01T12:00:00+01:00",
            valid_until="2026-10-31T23:59:59+01:00",
            last_seen_at="2026-09-28T16:00:00+01:00",
            is_active=True,
            days_of_week=[Weekday.MONDAY, Weekday.FRIDAY],
            dispatch_methods=[DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY],
            target_audience=TargetAudience.INDIVIDUAL,
            store_scope=StoreScope.SPECIFIC_STORES,
            store_ids=["2"],
            store_names=["Amoreiras"],
            pizza_count=1,
            pizza_size=PizzaSize.MEDIUM,
            included_items=[
                OfferComponent(category=ComponentCategory.PIZZA, quantity=1, size=PizzaSize.MEDIUM)
            ],
            image_url="https://example.com/promo.jpg",
            source_url="https://papajohns.pt/promocoes",
            location_scope="Lisboa",
        )

    def test_valid_promo_passes_validation(self) -> None:
        """Confirma que um registo perfeitamente conforme passa sem erros."""
        result = validate_promo(self.valid_promo)
        self.assertEqual(result.id, "promo-valida-1")

    def test_valid_dict_passes_validation(self) -> None:
        """Confirma que um dicionário com formato válido é validado com sucesso."""
        promo_dict = self.valid_promo.to_dict()
        result = validate_promo(promo_dict)
        self.assertIsInstance(result, UnifiedPromo)
        self.assertEqual(result.vendor, Brand.PAPA_JOHNS)
        self.assertEqual(result.price_cents, 1190)

    # --- Testes de Temporalidade e Timezone Awareness ---

    def test_missing_or_empty_observed_at_fails(self) -> None:
        """Validação falha se observed_at for ausente ou vazio."""
        promo = UnifiedPromo(
            id="obs-missing",
            vendor=Brand.DOMINOS,
            title="Oferta",
            description="",
            observed_at="",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("observed_at" in err for err in ctx.exception.errors))

    def test_timezone_naive_observed_at_fails(self) -> None:
        """Validação falha se observed_at for ingénuo (sem fuso horário explícito)."""
        promo = UnifiedPromo(
            id="obs-naive",
            vendor=Brand.DOMINOS,
            title="Oferta",
            description="",
            observed_at="2026-09-28T16:00:00",  # Sem timezone (+01:00 ou Z)
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("timezone-aware" in err for err in ctx.exception.errors))

    def test_timezone_aware_observed_at_with_z_passes(self) -> None:
        """Validação aceita ISO 8601 com sufixo Z ou offset explícito."""
        promo = UnifiedPromo(
            id="obs-z",
            vendor=Brand.DOMINOS,
            title="Oferta Z",
            description="",
            observed_at="2026-09-28T15:00:00Z",
        )
        result = validate_promo(promo)
        self.assertEqual(result.id, "obs-z")

    # --- Testes de Dinheiro Determinístico (Integer Cents) ---

    def test_float_price_cents_is_rejected(self) -> None:
        """Validação rejeita float em price_cents para forçar inteiros determinísticos."""
        promo = UnifiedPromo(
            id="float-price",
            vendor=Brand.DOMINOS,
            title="Preço Float",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
            price_cents=12.50,  # type: ignore[arg-type]
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("price_cents" in err for err in ctx.exception.errors))

    def test_negative_price_cents_fails(self) -> None:
        """Validação falha com cêntimos negativos."""
        promo = UnifiedPromo(
            id="neg-cents",
            vendor=Brand.PIZZA_HUT,
            title="Preço Negativo",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
            price_cents=-500,
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("price_cents" in err for err in ctx.exception.errors))

    def test_promotional_price_cents_greater_than_original_fails(self) -> None:
        """Validação falha se o preço promocional for maior que o original."""
        promo = UnifiedPromo(
            id="inv-prices",
            vendor=Brand.DOMINOS,
            title="Preço Inflacionado",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
            price_cents=2500,
            original_price_cents=2000,
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("não pode ser superior ao preço original" in err for err in ctx.exception.errors))

    # --- Testes de Aplicabilidade Geográfica e Lojas ---

    def test_specific_stores_without_store_ids_or_names_fails(self) -> None:
        """Validação falha se store_scope=SPECIFIC_STORES não especificar nenhuma loja."""
        promo = UnifiedPromo(
            id="spec-empty",
            vendor=Brand.DOMINOS,
            title="Oferta de Loja Sem Loja",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
            store_scope=StoreScope.SPECIFIC_STORES,
            store_ids=[],
            store_names=[],
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("SPECIFIC_STORES" in err for err in ctx.exception.errors))

    def test_invalid_location_scope_fails(self) -> None:
        """Validação falha se location_scope divergir de 'Lisboa'."""
        promo = UnifiedPromo(
            id="tp-porto",
            vendor=Brand.TELEPIZZA,
            title="Promo Porto",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
            location_scope="Porto",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("location_scope" in err for err in ctx.exception.errors))

    # --- Testes de Conteúdo e Componentes ---

    def test_invalid_pizza_count_fails(self) -> None:
        """Validação falha se pizza_count for zero, negativo ou float."""
        promo_zero = UnifiedPromo(
            id="pz-zero",
            vendor=Brand.PAPA_JOHNS,
            title="Zero Pizzas",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
            pizza_count=0,
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo_zero)
        self.assertTrue(any("pizza_count" in err for err in ctx.exception.errors))

    def test_invalid_included_items_quantity_fails(self) -> None:
        """Validação falha se algum componente tiver quantidade menor que 1."""
        promo = UnifiedPromo(
            id="bad-item",
            vendor=Brand.PAPA_JOHNS,
            title="Item Inválido",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
            included_items=[
                OfferComponent(category=ComponentCategory.PIZZA, quantity=0)
            ],
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("included_items" in err for err in ctx.exception.errors))

    # --- Testes Gerais de Validação ---

    def test_missing_or_blank_id_fails(self) -> None:
        """Validação falha se id for nulo, vazio ou só espaços."""
        promo = UnifiedPromo(
            id="   ",
            vendor=Brand.DOMINOS,
            title="Título",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("id" in err for err in ctx.exception.errors))

    def test_missing_or_blank_title_fails(self) -> None:
        """Validação falha se title for vazio."""
        promo = UnifiedPromo(
            id="d-1",
            vendor=Brand.DOMINOS,
            title="",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("title" in err for err in ctx.exception.errors))

    def test_invalid_discount_percentage_fails(self) -> None:
        """Validação falha com percentagens menores que 0 ou maiores que 100."""
        promo = UnifiedPromo(
            id="disc-err",
            vendor=Brand.PIZZA_HUT,
            title="Desconto Impossível",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
            discount_percentage=150.0,
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("discount_percentage" in err for err in ctx.exception.errors))

    def test_empty_dispatch_methods_fails(self) -> None:
        """Validação falha se dispatch_methods for lista vazia."""
        promo = UnifiedPromo(
            id="no-dispatch",
            vendor=Brand.TELEPIZZA,
            title="Sem Métodos",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
            dispatch_methods=[],
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("dispatch_methods" in err for err in ctx.exception.errors))

    def test_inverted_dates_fails(self) -> None:
        """Validação falha se valid_from for posterior a valid_until."""
        promo = UnifiedPromo(
            id="inv-dates",
            vendor=Brand.DOMINOS,
            title="Datas Invertidas",
            description="",
            observed_at="2026-09-28T16:00:00+01:00",
            valid_from="2026-12-31",
            valid_until="2026-01-01",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("posterior" in err for err in ctx.exception.errors))

    def test_batch_validation_success_and_failure(self) -> None:
        """Validação em lote processa itens válidos e agrega erros indexados."""
        items_valid = [self.valid_promo, self.valid_promo]
        self.assertEqual(len(validate_promos(items_valid)), 2)

        bad_item = UnifiedPromo(
            id="",
            vendor=Brand.DOMINOS,
            title="",
            description="",
            observed_at="",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promos([self.valid_promo, bad_item])
        self.assertTrue(any("[Item 1]" in err for err in ctx.exception.errors))


if __name__ == "__main__":
    unittest.main()
