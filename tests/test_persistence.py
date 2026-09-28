"""Testes unitários determinísticos para a camada de persistência relacional."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from pizza_radar.core.models import (
    Brand,
    DiscountType,
    DispatchMethod,
    OfferComponent,
    PizzaSize,
    StoreScope,
    UnifiedPromo,
    Weekday,
)
from pizza_radar.persistence.exporter import export_snapshot, generate_snapshot_dict
from pizza_radar.persistence.repository import (
    ObservationEntry,
    SQLitePromotionRepository,
)


class TestPersistenceRepository(unittest.TestCase):
    """Testa operações de base de dados e conformidade relacional com SQLite/libSQL."""

    def setUp(self) -> None:
        self.repo = SQLitePromotionRepository(db_path=":memory:")

    def _sample_promo(
        self,
        promo_id: str = "pj_101_in_store",
        vendor: Brand = Brand.PAPA_JOHNS,
        price_cents: int = 1200,
        original_price_cents: int | None = 1600,
        valid_until: str | None = None,
        observed_at: str = "2026-09-28T10:00:00+00:00",
        pizza_count: int | None = 2,
    ) -> UnifiedPromo:
        return UnifiedPromo(
            id=promo_id,
            vendor=vendor,
            title="Promo Teste",
            description="Descrição da promoção",
            observed_at=observed_at,
            price_cents=price_cents,
            original_price_cents=original_price_cents,
            discount_percentage=25.0,
            discount_type=DiscountType.FIXED_PRICE,
            store_scope=StoreScope.SPECIFIC_STORES,
            store_ids=["2", "13"],
            store_names=["Amoreiras", "Areeiro"],
            pizza_count=pizza_count,
            pizza_size=PizzaSize.MEDIUM,
            dispatch_methods=[DispatchMethod.TAKE_AWAY],
            valid_until=valid_until,
            source_url="https://papajohns.pt/promocoes",
        )

    def test_schema_initialization(self) -> None:
        conn = self.repo._get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ).fetchall()
        table_names = [r["name"] for r in tables]
        self.assertIn("promotions", table_names)
        self.assertIn("promotion_stores", table_names)
        self.assertIn("stores", table_names)
        self.assertIn("observation_history", table_names)
        self.assertIn("vendor_sync_runs", table_names)

    def test_upsert_stores(self) -> None:
        stores = [
            {
                "store_id": "2",
                "vendor": Brand.PAPA_JOHNS,
                "name": "Amoreiras",
                "postal_code": "1070-103",
                "address": "Av. Eng. Duarte Pacheco",
                "is_lisbon_municipality": True,
            }
        ]
        self.repo.upsert_stores(stores)
        conn = self.repo._get_connection()
        row = conn.execute("SELECT * FROM stores WHERE store_id = '2';").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "Amoreiras")
        self.assertEqual(row["vendor"], "PAPA_JOHNS")

    def test_upsert_new_promotions(self) -> None:
        p1 = self._sample_promo("pj_1", Brand.PAPA_JOHNS, 1000)
        p2 = self._sample_promo("pj_2", Brand.PAPA_JOHNS, 1500)

        stats = self.repo.upsert_promotions([p1, p2], vendor=Brand.PAPA_JOHNS)
        self.assertEqual(stats.created, 2)
        self.assertEqual(stats.updated, 0)

        active = self.repo.get_active_promotions()
        self.assertEqual(len(active), 2)
        p1_db = self.repo.get_promotion_by_id("pj_1")
        self.assertIsNotNone(p1_db)
        self.assertEqual(p1_db.price_cents, 1000)
        self.assertTrue(p1_db.is_active)

    def test_upsert_preserves_observed_at_and_tracks_price_changes(self) -> None:
        t1 = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
        p1 = self._sample_promo("pj_1", Brand.PAPA_JOHNS, 1000, observed_at=t1.isoformat())
        self.repo.upsert_promotions([p1], vendor=Brand.PAPA_JOHNS, sync_time=t1)

        t2 = datetime(2026, 9, 28, 17, 0, tzinfo=timezone.utc)
        # Preço alterado de 1000 para 1100
        p1_mod = self._sample_promo("pj_1", Brand.PAPA_JOHNS, 1100, observed_at=t2.isoformat())
        stats = self.repo.upsert_promotions([p1_mod], vendor=Brand.PAPA_JOHNS, sync_time=t2)

        self.assertEqual(stats.created, 0)
        self.assertEqual(stats.updated, 1)
        self.assertEqual(stats.price_changed, 1)

        retrieved = self.repo.get_promotion_by_id("pj_1")
        self.assertIsNotNone(retrieved)
        # observed_at original deve ser preservado
        self.assertEqual(retrieved.observed_at, t1.isoformat())
        # last_seen_at deve refletir a nova execução
        self.assertEqual(retrieved.last_seen_at, t2.isoformat())
        self.assertEqual(retrieved.price_cents, 1100)

        # Confirmar que ambas as observações foram registadas no histórico
        conn = self.repo._get_connection()
        history = conn.execute(
            "SELECT price_cents, is_available FROM observation_history WHERE promotion_id = 'pj_1' ORDER BY id ASC;"
        ).fetchall()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["price_cents"], 1000)
        self.assertEqual(history[1]["price_cents"], 1100)

    def test_consecutive_misses_and_deactivation(self) -> None:
        t1 = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
        p1 = self._sample_promo("pj_1", Brand.PAPA_JOHNS, 1000)
        p2 = self._sample_promo("pj_2", Brand.PAPA_JOHNS, 1200)
        self.repo.upsert_promotions([p1, p2], vendor=Brand.PAPA_JOHNS, sync_time=t1)

        # Sincronização 2: p2 desapareceu do lote
        t2 = datetime(2026, 9, 28, 17, 0, tzinfo=timezone.utc)
        stats2 = self.repo.upsert_promotions([p1], vendor=Brand.PAPA_JOHNS, sync_time=t2)
        self.assertEqual(stats2.misses_incremented, 1)
        self.assertEqual(stats2.deactivated_by_misses, 0)

        # p2 ainda deve estar ativo com consecutive_misses = 1
        p2_db = self.repo.get_promotion_by_id("pj_2")
        self.assertTrue(p2_db.is_active)
        conn = self.repo._get_connection()
        row_p2 = conn.execute("SELECT consecutive_misses, is_active FROM promotions WHERE id = 'pj_2';").fetchone()
        self.assertEqual(row_p2["consecutive_misses"], 1)
        self.assertEqual(row_p2["is_active"], 1)

        # Sincronização 3: p2 ausente pela 2ª vez consecutiva -> deve desativar (max_misses=2)
        t3 = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
        stats3 = self.repo.upsert_promotions([p1], vendor=Brand.PAPA_JOHNS, sync_time=t3)
        self.assertEqual(stats3.misses_incremented, 1)
        self.assertEqual(stats3.deactivated_by_misses, 1)

        p2_db_after = self.repo.get_promotion_by_id("pj_2")
        self.assertFalse(p2_db_after.is_active)

        # get_active_promotions deve retornar apenas p1
        active = self.repo.get_active_promotions()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].id, "pj_1")

        # Sincronização 4: p2 reaparece na fonte -> deve reativar
        t4 = datetime(2026, 9, 29, 17, 0, tzinfo=timezone.utc)
        stats4 = self.repo.upsert_promotions([p1, p2], vendor=Brand.PAPA_JOHNS, sync_time=t4)
        self.assertEqual(stats4.reactivated, 1)
        p2_reactivated = self.repo.get_promotion_by_id("pj_2")
        self.assertTrue(p2_reactivated.is_active)

    def test_expiration_by_valid_until_date(self) -> None:
        now = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
        p_expired = self._sample_promo(
            "pj_exp", Brand.PAPA_JOHNS, 900, valid_until="2026-09-28T11:00:00+00:00"
        )
        p_valid = self._sample_promo(
            "pj_val", Brand.PAPA_JOHNS, 900, valid_until="2026-09-28T23:59:59+00:00"
        )
        p_indefinite = self._sample_promo("pj_indef", Brand.PAPA_JOHNS, 900, valid_until=None)

        self.repo.upsert_promotions([p_expired, p_valid, p_indefinite], vendor=Brand.PAPA_JOHNS)
        self.assertEqual(len(self.repo.get_active_promotions()), 3)

        expired_count = self.repo.expire_outdated_promotions(reference_time=now)
        self.assertEqual(expired_count, 1)

        active = self.repo.get_active_promotions()
        self.assertEqual(len(active), 2)
        active_ids = {p.id for p in active}
        self.assertIn("pj_val", active_ids)
        self.assertIn("pj_indef", active_ids)
        self.assertNotIn("pj_exp", active_ids)

    def test_vendor_sync_runs_logging(self) -> None:
        run_id = self.repo.record_vendor_sync_run(
            vendor=Brand.DOMINOS,
            status="SUCCESS",
            offers_found=15,
        )
        self.assertGreater(run_id, 0)

        self.repo.record_vendor_sync_run(
            vendor=Brand.TELEPIZZA,
            status="FAILED",
            offers_found=0,
            error_message="NetworkError: Connection timed out",
        )

        runs = self.repo.get_vendor_sync_runs()
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0]["vendor"], "TELEPIZZA")
        self.assertEqual(runs[0]["status"], "FAILED")
        self.assertEqual(runs[1]["vendor"], "DOMINOS")
        self.assertEqual(runs[1]["status"], "SUCCESS")

    def test_snapshot_export_determinism(self) -> None:
        p1 = self._sample_promo("pj_1", Brand.PAPA_JOHNS, 1000, pizza_count=2)
        p2 = self._sample_promo("dom_1", Brand.DOMINOS, 800, pizza_count=1)
        self.repo.upsert_promotions([p1], vendor=Brand.PAPA_JOHNS)
        self.repo.upsert_promotions([p2], vendor=Brand.DOMINOS)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "data" / "promotions.json"
            snapshot = export_snapshot(self.repo, out_file)

            self.assertTrue(out_file.exists())
            self.assertEqual(snapshot["location_scope"], "Lisboa")
            self.assertEqual(snapshot["stats"]["total_offers"], 2)
            self.assertEqual(snapshot["stats"]["total_groups"], 2)
            self.assertEqual(snapshot["stats"]["min_price_cents"], 800)
            self.assertIn("DOMINOS", snapshot["vendors_active"])
            self.assertIn("PAPA_JOHNS", snapshot["vendors_active"])
            self.assertEqual(len(snapshot["groups"]), 2)


if __name__ == "__main__":
    unittest.main()
