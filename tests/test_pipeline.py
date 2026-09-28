"""Testes unitários determinísticos para a pipeline de orquestração e tolerância a falhas."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from pizza_radar.core.adapter import PromoAdapterInterface
from pizza_radar.core.models import (
    Brand,
    DiscountType,
    DispatchMethod,
    PizzaSize,
    StoreScope,
    UnifiedPromo,
)
from pizza_radar.persistence.repository import (
    LibSqlPromotionRepository,
    SQLitePromotionRepository,
    TursoPromotionRepository,
)
from pizza_radar.pipeline.cli import build_repository, main as cli_main
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

    def test_pipeline_snapshot_data_mode_live(self) -> None:
        p_pj = self._make_promo("pj_1", Brand.PAPA_JOHNS, 1200)
        adapter = MockAdapter(Brand.PAPA_JOHNS, [p_pj])

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_file = Path(tmpdir) / "promotions.json"
            result = run_pipeline(
                repo=self.repo,
                adapters=[adapter],
                snapshot_output_path=snapshot_file,
                data_mode="live",
            )
            self.assertTrue(result.success)
            with open(snapshot_file, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data.get("data_mode"), "live")

    def test_pipeline_snapshot_data_mode_demo(self) -> None:
        p_pj = self._make_promo("pj_1", Brand.PAPA_JOHNS, 1200)
        adapter = MockAdapter(Brand.PAPA_JOHNS, [p_pj])

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_file = Path(tmpdir) / "promotions.json"
            result = run_pipeline(
                repo=self.repo,
                adapters=[adapter],
                snapshot_output_path=snapshot_file,
                data_mode="demo",
            )
            self.assertTrue(result.success)
            with open(snapshot_file, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data.get("data_mode"), "demo")

    def test_persistence_across_sequential_runs(self) -> None:
        """Verifica a persistência de observações entre execuções sequenciais."""
        t1 = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
        p1 = self._make_promo("pj_1", Brand.PAPA_JOHNS, 1000)
        p1.observed_at = t1.isoformat()
        res1 = run_pipeline(self.repo, [MockAdapter(Brand.PAPA_JOHNS, [p1])], sync_time=t1)
        self.assertTrue(res1.success)

        # Execução 2: Preço altera para 1100
        t2 = datetime(2026, 9, 28, 17, 0, tzinfo=timezone.utc)
        p1_updated = self._make_promo("pj_1", Brand.PAPA_JOHNS, 1100)
        p1_updated.observed_at = t2.isoformat()
        res2 = run_pipeline(self.repo, [MockAdapter(Brand.PAPA_JOHNS, [p1_updated])], sync_time=t2)
        self.assertTrue(res2.success)

        # A promoção na BD deve preservar o observed_at de t1 e ter o preço atualizado
        db_p1 = self.repo.get_promotion_by_id("pj_1")
        self.assertIsNotNone(db_p1)
        self.assertEqual(db_p1.observed_at, t1.isoformat())
        self.assertEqual(db_p1.last_seen_at, t2.isoformat())
        self.assertEqual(db_p1.price_cents, 1100)


class TestCliRepositorySelection(unittest.TestCase):
    """Testa a seleção estrita de repositórios e política fail-fast do CLI."""

    def test_cli_selects_sqlite_in_local_mode(self) -> None:
        import argparse

        # 1. Com flag --local
        args1 = argparse.Namespace(
            local=True, mode="scheduled", db_engine="turso", db_path=":memory:", database_url=None, auth_token=None
        )
        repo1, mode1 = build_repository(args1)
        self.assertIsInstance(repo1, SQLitePromotionRepository)
        self.assertEqual(mode1, "demo")

        # 2. Com --mode local
        args2 = argparse.Namespace(
            local=False, mode="local", db_engine="turso", db_path=":memory:", database_url=None, auth_token=None
        )
        repo2, mode2 = build_repository(args2)
        self.assertIsInstance(repo2, SQLitePromotionRepository)
        self.assertEqual(mode2, "demo")

        # 3. Com --db-engine sqlite
        args3 = argparse.Namespace(
            local=False, mode="scheduled", db_engine="sqlite", db_path=":memory:", database_url=None, auth_token=None
        )
        repo3, mode3 = build_repository(args3)
        self.assertIsInstance(repo3, SQLitePromotionRepository)
        self.assertEqual(mode3, "demo")

    def test_cli_selects_turso_in_scheduled_mode(self) -> None:
        import argparse

        args = argparse.Namespace(
            local=False,
            mode="scheduled",
            db_engine="turso",
            db_path="pizza_radar.db",
            database_url="libsql://my-org.turso.io",
            auth_token="valid-token",
        )
        with patch.object(TursoPromotionRepository, "init_schema", return_value=None):
            repo, mode = build_repository(args)
            self.assertIsInstance(repo, TursoPromotionRepository)
            self.assertEqual(mode, "live")

    def test_cli_missing_credentials_fails_fast_without_sqlite_fallback(self) -> None:
        import argparse

        args = argparse.Namespace(
            local=False,
            mode="scheduled",
            db_engine="turso",
            db_path="pizza_radar.db",
            database_url=None,
            auth_token=None,
        )
        with patch.dict("os.environ", {}, clear=True):
            repo, mode = build_repository(args)
            self.assertIsNone(repo)
            self.assertEqual(mode, "")

            # main() deve sair com código 1
            exit_code = cli_main(["--mode", "scheduled"])
            self.assertEqual(exit_code, 1)

    def test_cli_database_failure_fails_fast_without_snapshot_or_deploy(self) -> None:
        with patch.dict(
            "os.environ",
            {"TURSO_DATABASE_URL": "libsql://my-org.turso.io", "TURSO_AUTH_TOKEN": "some-token"},
        ):
            with patch.object(TursoPromotionRepository, "init_schema", side_effect=ConnectionError("Turso unreachable")):
                with tempfile.TemporaryDirectory() as tmpdir:
                    snap_out = Path(tmpdir) / "promotions.json"
                    exit_code = cli_main(["--mode", "scheduled", "--snapshot-output", str(snap_out)])
                    self.assertEqual(exit_code, 1)
                    # Snapshot não deve ter sido criado
                    self.assertFalse(snap_out.exists())


if __name__ == "__main__":
    unittest.main()
