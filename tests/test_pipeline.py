"""Testes unitários determinísticos para a pipeline de orquestração e tolerância a falhas."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from pizza_radar.core.adapter import PromoAdapterInterface
from pizza_radar.core.models import (
    Brand,
    DiscountType,
    DispatchMethod,
    PizzaSize,
    StoreScope,
    UnifiedPromo,
)
from pizza_radar.persistence.repository import SQLitePromotionRepository
from pizza_radar.pipeline.runner import run_pipeline


class MockAdapter(PromoAdapterInterface):
    """Adaptador de teste configurável."""

    def __init__(self, vendor: Brand, promos: list[UnifiedPromo] | None = None, raise_error: Exception | None = None) -> None:
        self._vendor = vendor
        self._promos = promos or []
        self._raise_error = raise_error

    @property
    def vendor(self) -> Brand:
        return self._vendor

    def fetch_raw(self) -> dict | list | str:
        if self._raise_error:
            raise self._raise_error
        return {}

    def parse(self, raw_data: dict | list | str) -> list[dict]:
        return []

    def adapt(self, parsed_items: list[dict]) -> list[UnifiedPromo]:
        return self._promos

    def fetch_promotions(self) -> list[UnifiedPromo]:
        if self._raise_error:
            raise self._raise_error
        return self._promos


class TestPipelineRunner(unittest.TestCase):
    """Testa a coordenação, isolamento de falhas e integridade do snapshot."""

    def setUp(self) -> None:
        self.repo = SQLitePromotionRepository(db_path=":memory:")

    def _make_promo(self, promo_id: str, vendor: Brand, price_cents: int = 1000) -> UnifiedPromo:
        return UnifiedPromo(
            id=promo_id,
            vendor=vendor,
            title=f"Promo {promo_id}",
            description="Descrição",
            observed_at="2026-09-28T12:00:00+00:00",
            price_cents=price_cents,
            discount_type=DiscountType.FIXED_PRICE,
            store_scope=StoreScope.SPECIFIC_STORES,
            store_ids=["1"],
            pizza_count=1,
            dispatch_methods=[DispatchMethod.DELIVERY],
            source_url="https://exemplo.pt",
        )

    def test_run_pipeline_all_success(self) -> None:
        p_pj = self._make_promo("pj_1", Brand.PAPA_JOHNS, 1200)
        p_dom = self._make_promo("dom_1", Brand.DOMINOS, 1100)

        adapters = [
            MockAdapter(Brand.PAPA_JOHNS, [p_pj]),
            MockAdapter(Brand.DOMINOS, [p_dom]),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_file = Path(tmpdir) / "data" / "promotions.json"
            result = run_pipeline(
                repo=self.repo,
                adapters=adapters,
                snapshot_output_path=snapshot_file,
            )

            self.assertTrue(result.success)
            self.assertTrue(result.snapshot_exported)
            self.assertEqual(result.total_active_promotions, 2)
            self.assertEqual(result.vendor_results["PAPA_JOHNS"].status, "SUCCESS")
            self.assertEqual(result.vendor_results["DOMINOS"].status, "SUCCESS")
            self.assertTrue(snapshot_file.exists())

    def test_vendor_failure_isolation_preserves_promotions_and_misses(self) -> None:
        """Regra Crítica: Uma falha de um operador NÃO desativa as suas ofertas pré-existentes

        nem incrementa o seu contador consecutive_misses.
        """
        # 1. Execução inicial onde Papa John's e Domino's sincronizam com sucesso
        p_pj = self._make_promo("pj_1", Brand.PAPA_JOHNS, 1200)
        p_dom = self._make_promo("dom_1", Brand.DOMINOS, 1100)

        adapters_run1 = [
            MockAdapter(Brand.PAPA_JOHNS, [p_pj]),
            MockAdapter(Brand.DOMINOS, [p_dom]),
        ]
        res1 = run_pipeline(self.repo, adapters_run1)
        self.assertTrue(res1.success)
        self.assertEqual(res1.total_active_promotions, 2)

        # 2. Execução 2: Domino's sofre falha de rede (NetworkError), Papa John's tem sucesso
        dom_error = ConnectionResetError("Falha de conexão com api.dominospizza.pt")
        adapters_run2 = [
            MockAdapter(Brand.PAPA_JOHNS, [p_pj]),
            MockAdapter(Brand.DOMINOS, raise_error=dom_error),
        ]

        res2 = run_pipeline(self.repo, adapters_run2)
        # Pipeline prossegue com sucesso global (isolando a falha do vendedor)
        self.assertTrue(res2.success)
        self.assertEqual(res2.vendor_results["DOMINOS"].status, "FAILED")
        self.assertIn("ConnectionResetError", res2.vendor_results["DOMINOS"].error_message or "")
        self.assertEqual(res2.vendor_results["PAPA_JOHNS"].status, "SUCCESS")

        # Invariante: a promoção de Domino's ainda deve estar ativa na BD!
        dom_promo = self.repo.get_promotion_by_id("dom_1")
        self.assertIsNotNone(dom_promo)
        self.assertTrue(dom_promo.is_active)

        # Invariante: consecutive_misses de Domino's NÃO foi incrementado!
        conn = self.repo._get_connection()
        row_dom = conn.execute("SELECT consecutive_misses FROM promotions WHERE id = 'dom_1';").fetchone()
        self.assertEqual(row_dom["consecutive_misses"], 0)

        # Total de ofertas ativas mantido
        self.assertEqual(res2.total_active_promotions, 2)

    def test_database_failure_aborts_snapshot_export(self) -> None:
        """Se ocorrer uma falha crítica na base de dados, a publicação é abortada."""
        p_pj = self._make_promo("pj_1", Brand.PAPA_JOHNS, 1200)
        adapter = MockAdapter(Brand.PAPA_JOHNS, [p_pj])

        # Mock repository que falha em get_active_promotions
        mock_repo = MagicMock(spec=SQLitePromotionRepository)
        mock_repo.upsert_promotions.return_value = MagicMock()
        mock_repo.get_active_promotions.side_effect = RuntimeError("Base de dados bloqueada")

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_file = Path(tmpdir) / "promotions.json"
            # Cria ficheiro pré-existente
            snapshot_file.write_text('{"existing": true}', encoding="utf-8")

            result = run_pipeline(
                repo=mock_repo,
                adapters=[adapter],
                snapshot_output_path=snapshot_file,
            )

            self.assertFalse(result.success)
            self.assertFalse(result.snapshot_exported)
            # Ficheiro pré-existente não foi corrompido/substituído
            self.assertEqual(snapshot_file.read_text(encoding="utf-8"), '{"existing": true}')


if __name__ == "__main__":
    unittest.main()
