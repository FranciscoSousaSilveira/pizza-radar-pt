"""Testes unitários determinísticos do catálogo e cálculo de horários de lojas de Lisboa."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta
from pizza_radar.core.models import Brand, DispatchMethod
from pizza_radar.data.lisbon_stores import (
    LISBON_STORES_CATALOG,
    LisbonStore,
    get_lisbon_offset,
    to_lisbon_time,
    get_store_status_at,
)


class TestLisbonStoresCatalog(unittest.TestCase):
    """Testa integridade e regras de negócio do catálogo de 33 lojas de Lisboa."""

    def test_catalog_store_count_and_brands(self):
        """Verifica que o catálogo contém exatamente as 33 lojas oficiais de Lisboa."""
        self.assertEqual(len(LISBON_STORES_CATALOG), 33)

        by_brand = {}
        for store in LISBON_STORES_CATALOG:
            by_brand[store.brand] = by_brand.get(store.brand, 0) + 1

        self.assertEqual(by_brand[Brand.DOMINOS], 8)
        self.assertEqual(by_brand[Brand.PAPA_JOHNS], 3)
        self.assertEqual(by_brand[Brand.PIZZA_HUT], 12)
        self.assertEqual(by_brand[Brand.TELEPIZZA], 10)

    def test_store_attributes_and_services(self):
        """Garante que todas as lojas têm IDs únicos, moradas, telefones e serviços válidos."""
        ids = set()
        for store in LISBON_STORES_CATALOG:
            self.assertNotIn(store.id, ids)
            ids.add(store.id)
            self.assertTrue(store.name)
            self.assertTrue(store.neighborhood)
            self.assertTrue(store.address)
            self.assertTrue("Lisboa" in store.address or "1" in store.address)
            self.assertTrue(store.phone)
            self.assertTrue(store.official_url.startswith("http"))
            self.assertTrue(len(store.services) >= 1)
            # Serviços conhecidos
            for s in store.services:
                self.assertIn(s, (DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY, DispatchMethod.DINE_IN))
            # Horários para os 7 dias da semana (0=Dom a 6=Sáb)
            for d in range(7):
                self.assertIn(str(d), store.schedule)
                self.assertTrue(store.schedule[str(d)].open)
                self.assertTrue(store.schedule[str(d)].close)


class TestLisbonTimeAndStatus(unittest.TestCase):
    """Testa conversão de timezone de Lisboa e cálculo determinístico de estado."""

    def test_lisbon_offset_winter_and_summer(self):
        """Verifica WET (UTC+0 no inverno) e WEST (UTC+1 no verão)."""
        # Janeiro (Inverno): UTC+0
        dt_jan = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(get_lisbon_offset(dt_jan), timedelta(hours=0))
        lisbon_jan = to_lisbon_time(dt_jan)
        self.assertEqual(lisbon_jan.hour, 12)

        # Julho (Verão): UTC+1
        dt_jul = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(get_lisbon_offset(dt_jul), timedelta(hours=1))
        lisbon_jul = to_lisbon_time(dt_jul)
        self.assertEqual(lisbon_jul.hour, 13)

    def test_store_open_during_day(self):
        """Loja com horário 11:30 às 00:00 deve estar aberta às 15:00."""
        store = next(s for s in LISBON_STORES_CATALOG if s.id == "dom_areeiro")
        # Quarta-feira às 15:00 em Lisboa (UTC+1 em outubro se DST ativo ou UTC+0)
        dt = datetime(2026, 10, 7, 14, 0, tzinfo=timezone.utc) # 15:00 Lisboa
        status = get_store_status_at(store, dt)
        self.assertTrue(status["is_open"])
        self.assertFalse(status["closing_soon"])
        self.assertEqual(status["status_code"], "OPEN")
        self.assertIn("Aberta agora", status["label"])

    def test_store_closed_early_morning(self):
        """Loja deve estar fechada às 08:00 e indicar abertura às 11:30."""
        store = next(s for s in LISBON_STORES_CATALOG if s.id == "dom_areeiro")
        dt = datetime(2026, 10, 7, 7, 0, tzinfo=timezone.utc) # 08:00 Lisboa
        status = get_store_status_at(store, dt)
        self.assertFalse(status["is_open"])
        self.assertEqual(status["status_code"], "CLOSED")
        self.assertIn("Abre hoje às 11:30", status["label"])

    def test_store_closing_soon(self):
        """Loja que fecha às 00:00 deve reportar CLOSING_SOON às 23:45."""
        store = next(s for s in LISBON_STORES_CATALOG if s.id == "dom_areeiro")
        dt = datetime(2026, 10, 7, 22, 45, tzinfo=timezone.utc) # 23:45 Lisboa
        status = get_store_status_at(store, dt)
        self.assertTrue(status["is_open"])
        self.assertTrue(status["closing_soon"])
        self.assertEqual(status["status_code"], "CLOSING_SOON")
        self.assertIn("Fecha em breve às 00:00", status["label"])

    def test_store_past_midnight_extended_hours(self):
        """Loja na sexta-feira à noite fecha à 01:00 de sábado. Às 00:30 de sábado deve estar aberta."""
        store = next(s for s in LISBON_STORES_CATALOG if s.id == "dom_areeiro")
        # 2026-10-10 é Sábado. Às 00:30 de Lisboa (23:30 UTC de sexta-feira 2026-10-09)
        dt_saturday_night = datetime(2026, 10, 9, 23, 30, tzinfo=timezone.utc)
        status = get_store_status_at(store, dt_saturday_night)
        self.assertTrue(status["is_open"])
        # Fecha à 01:00, às 00:30 faltam 30 minutos -> CLOSING_SOON
        self.assertTrue(status["closing_soon"])
        self.assertEqual(status["status_code"], "CLOSING_SOON")
        self.assertIn("01:00", status["label"])


if __name__ == "__main__":
    unittest.main()
