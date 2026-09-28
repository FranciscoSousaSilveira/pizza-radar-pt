"""Testes unitários para o validador do UnifiedPromo."""

import unittest

from pizza_radar.core.models import (
    Brand,
    DispatchMethod,
    DiscountType,
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
            price=11.90,
            original_price=15.90,
            discount_percentage=25.2,
            discount_type=DiscountType.FIXED_PRICE,
            conditions="Válido de segunda a sexta no concelho de Lisboa.",
            valid_from="2026-09-01T12:00:00",
            valid_until="2026-10-31T23:59:59",
            days_of_week=[Weekday.MONDAY, Weekday.FRIDAY],
            dispatch_methods=[DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY],
            target_audience=TargetAudience.INDIVIDUAL,
            image_url="https://example.com/promo.jpg",
            source_url="https://papajohns.pt/promocoes",
            scraped_at="2026-09-28T16:00:00",
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

    def test_missing_or_blank_id(self) -> None:
        """Validação falha se id for nulo, vazio ou só espaços."""
        promo = UnifiedPromo(
            id="   ",
            vendor=Brand.DOMINOS,
            title="Título Válido",
            description="Desc",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("id" in err for err in ctx.exception.errors))

    def test_missing_or_blank_title(self) -> None:
        """Validação falha se title for vazio."""
        promo = UnifiedPromo(
            id="d-1",
            vendor=Brand.DOMINOS,
            title="",
            description="Desc",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("title" in err for err in ctx.exception.errors))

    def test_invalid_location_scope(self) -> None:
        """Validação falha se location_scope não for 'Lisboa'."""
        promo = UnifiedPromo(
            id="tp-porto",
            vendor=Brand.TELEPIZZA,
            title="Promo Porto",
            description="Fora de Lisboa",
            location_scope="Porto",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("location_scope" in err for err in ctx.exception.errors))

    def test_negative_prices(self) -> None:
        """Validação falha com preços negativos."""
        promo = UnifiedPromo(
            id="ph-neg",
            vendor=Brand.PIZZA_HUT,
            title="Preço Negativo",
            description="Desc",
            price=-5.00,
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("price" in err for err in ctx.exception.errors))

    def test_promotional_price_greater_than_original(self) -> None:
        """Validação falha se o preço promocional for maior que o original."""
        promo = UnifiedPromo(
            id="d-invalid-prices",
            vendor=Brand.DOMINOS,
            title="Preço Inflacionado",
            description="Desc",
            price=25.00,
            original_price=20.00,
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("superior ao preço original" in err for err in ctx.exception.errors))

    def test_invalid_discount_percentage(self) -> None:
        """Validação falha com percentagens menores que 0 ou maiores que 100."""
        promo = UnifiedPromo(
            id="ph-disc-err",
            vendor=Brand.PIZZA_HUT,
            title="Desconto Impossível",
            description="Desc",
            discount_percentage=150.0,
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("discount_percentage" in err for err in ctx.exception.errors))

    def test_empty_dispatch_methods(self) -> None:
        """Validação falha se a lista de canais de atendimento estiver vazia."""
        promo = UnifiedPromo(
            id="tp-no-dispatch",
            vendor=Brand.TELEPIZZA,
            title="Sem Métodos de Atendimento",
            description="Desc",
            dispatch_methods=[],
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo)
        self.assertTrue(any("dispatch_methods" in err for err in ctx.exception.errors))

    def test_invalid_dates(self) -> None:
        """Validação falha com datas mal formatadas ou com intervalo invertido."""
        promo_bad_format = UnifiedPromo(
            id="bad-date",
            vendor=Brand.DOMINOS,
            title="Data Inválida",
            description="Desc",
            valid_from="amanhã",
        )
        with self.assertRaises(ValidationError):
            validate_promo(promo_bad_format)

        promo_inverted_dates = UnifiedPromo(
            id="inverted-dates",
            vendor=Brand.DOMINOS,
            title="Datas Invertidas",
            description="Desc",
            valid_from="2026-12-31",
            valid_until="2026-01-01",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo_inverted_dates)
        self.assertTrue(any("posterior" in err for err in ctx.exception.errors))

    def test_invalid_urls(self) -> None:
        """Validação falha com URLs de fonte ou imagem inválidos."""
        promo_bad_url = UnifiedPromo(
            id="bad-url",
            vendor=Brand.PAPA_JOHNS,
            title="URL Inválido",
            description="Desc",
            source_url="javascript:alert(1)",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_promo(promo_bad_url)
        self.assertTrue(any("source_url" in err for err in ctx.exception.errors))

    def test_batch_validation_success(self) -> None:
        """Valida que uma lista homogénea de registos válidos é processada corretamente."""
        items = [self.valid_promo, self.valid_promo]
        results = validate_promos(items)
        self.assertEqual(len(results), 2)

    def test_batch_validation_failure_aggregates_errors(self) -> None:
        """Valida que falhas em lote agregam erros indicando o índice de cada item."""
        bad_item = UnifiedPromo(
            id="",
            vendor=Brand.DOMINOS,
            title="",
            description="",
        )
        items = [self.valid_promo, bad_item]
        with self.assertRaises(ValidationError) as ctx:
            validate_promos(items)
        self.assertTrue(any("[Item 1]" in err for err in ctx.exception.errors))


if __name__ == "__main__":
    unittest.main()
