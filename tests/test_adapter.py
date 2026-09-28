"""Testes unitários para a interface de adaptadores e classes de exceção."""

import unittest

from pizza_radar.core.adapter import (
    AdapterError,
    NetworkError,
    ParseError,
    PromoAdapterInterface,
    RateLimitError,
)
from pizza_radar.core.models import (
    Brand,
    DiscountType,
    PizzaSize,
    StoreScope,
    UnifiedPromo,
)


class MockPapaJohnsAdapter(PromoAdapterInterface):
    """Implementação mock para teste de conformidade da interface."""

    def __init__(self, should_fail_network: bool = False, should_fail_parse: bool = False) -> None:
        self.should_fail_network = should_fail_network
        self.should_fail_parse = should_fail_parse

    @property
    def vendor(self) -> Brand:
        return Brand.PAPA_JOHNS

    def fetch_promotions(self, timeout: float = 10.0) -> list[UnifiedPromo]:
        if self.should_fail_network:
            raise NetworkError("Falha de conexão com a API", vendor=self.vendor)
        if self.should_fail_parse:
            raise ParseError("JSON malformado recebido", vendor=self.vendor)

        return [
            UnifiedPromo(
                id="mock-pj-1",
                vendor=self.vendor,
                title="Super Terça",
                description="Duas pizzas médias por 15€",
                observed_at="2026-09-28T16:00:00+01:00",
                price_cents=1500,
                original_price_cents=2400,
                discount_type=DiscountType.X_FOR_Y,
                store_scope=StoreScope.SPECIFIC_STORES,
                store_ids=["2"],
                store_names=["Amoreiras"],
                pizza_count=2,
                pizza_size=PizzaSize.MEDIUM,
                source_url="https://papajohns.pt/promocoes",
                location_scope="Lisboa",
            )
        ]


class TestPromoAdapterInterface(unittest.TestCase):
    """Testes de conformidade da interface de adaptadores."""

    def test_mock_adapter_compliance(self) -> None:
        """Verifica se o adaptador mock implementa a interface e devolve promoções válidas."""
        adapter = MockPapaJohnsAdapter()
        self.assertEqual(adapter.vendor, Brand.PAPA_JOHNS)

        promos = adapter.fetch_promotions()
        self.assertEqual(len(promos), 1)
        self.assertEqual(promos[0].id, "mock-pj-1")
        self.assertEqual(promos[0].price_cents, 1500)
        self.assertEqual(promos[0].price_euros, 15.00)
        self.assertTrue(promos[0].is_comparable_for_unit_price)
        self.assertEqual(promos[0].price_per_pizza_cents, 750)

        # Teste do método de validação do adaptador
        validated = adapter.validate_and_filter(promos)
        self.assertEqual(len(validated), 1)
        self.assertEqual(validated[0].vendor, Brand.PAPA_JOHNS)

    def test_adapter_network_error(self) -> None:
        """Verifica propagação estruturada de NetworkError."""
        adapter = MockPapaJohnsAdapter(should_fail_network=True)
        with self.assertRaises(NetworkError) as ctx:
            adapter.fetch_promotions()
        self.assertEqual(ctx.exception.vendor, Brand.PAPA_JOHNS)
        self.assertIn("Falha de conexão", str(ctx.exception))

    def test_adapter_parse_error(self) -> None:
        """Verifica propagação estruturada de ParseError."""
        adapter = MockPapaJohnsAdapter(should_fail_parse=True)
        with self.assertRaises(ParseError) as ctx:
            adapter.fetch_promotions()
        self.assertEqual(ctx.exception.vendor, Brand.PAPA_JOHNS)
        self.assertIn("JSON malformado", str(ctx.exception))

    def test_cannot_instantiate_abstract_interface_directly(self) -> None:
        """Verifica que a interface PromoAdapterInterface não pode ser instanciada diretamente."""
        with self.assertRaises(TypeError):
            PromoAdapterInterface()  # type: ignore[abstract]

    def test_exception_hierarchy(self) -> None:
        """Confirma a árvore de herança das exceções de adaptadores."""
        self.assertTrue(issubclass(NetworkError, AdapterError))
        self.assertTrue(issubclass(ParseError, AdapterError))
        self.assertTrue(issubclass(RateLimitError, AdapterError))
        self.assertTrue(issubclass(AdapterError, Exception))


if __name__ == "__main__":
    unittest.main()
