"""Testes unitários determinísticos para geocodificação e validação geográfica de Lisboa."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pizza_radar.data.geocoding import (
    GeocodedLocation,
    NominatimGeocoder,
    is_within_lisbon_bounds,
    validate_store_in_lisbon,
)


class TestGeocodingAndValidation(unittest.TestCase):
    """Testa lógica de limites geográficos de Lisboa e cliente Nominatim com cache."""

    def test_is_within_lisbon_bounds(self):
        """Verifica coordenadas conhecidas de Lisboa (Rossio, Areeiro, Parque das Nações) vs fora (Porto, Madrid, Cascais)."""
        # Dentro de Lisboa
        self.assertTrue(is_within_lisbon_bounds(38.7139, -9.1394))  # Rossio
        self.assertTrue(is_within_lisbon_bounds(38.7420, -9.1330))  # Areeiro
        self.assertTrue(is_within_lisbon_bounds(38.7675, -9.0970))  # Parque das Nações
        self.assertTrue(is_within_lisbon_bounds(38.7500, -9.2000))  # Benfica

        # Fora de Lisboa
        self.assertFalse(is_within_lisbon_bounds(41.1579, -8.6291))  # Porto
        self.assertFalse(is_within_lisbon_bounds(40.4168, -3.7038))  # Madrid
        self.assertFalse(is_within_lisbon_bounds(38.6970, -9.4200))  # Cascais (concelho vizinho)
        self.assertFalse(is_within_lisbon_bounds(38.6700, -9.1500))  # Almada (margem sul do Tejo)

    def test_geocoder_cache_and_mocked_network(self):
        """Verifica que o geocodificador grava e reutiliza cache sem repetir chamadas de rede."""
        sample_nominatim_resp = [
            {
                "lat": "38.7422",
                "lon": "-9.1332",
                "display_name": "Avenida Padre Manuel da Nóbrega, Areeiro, Lisboa, Portugal",
                "address": {
                    "city": "Lisboa",
                    "postcode": "1000-223",
                },
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "geo_cache.json"
            geocoder = NominatimGeocoder(cache_path=cache_file, request_delay=0.0)

            # Primeira chamada: simula resposta da rede
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps(sample_nominatim_resp).encode("utf-8")
                mock_urlopen.return_value.__enter__.return_value = mock_resp

                loc1 = geocoder.geocode("Av. Padre Manuel da Nóbrega 4A, Lisboa")

                self.assertIsNotNone(loc1)
                self.assertAlmostEqual(loc1.latitude, 38.7422)
                self.assertAlmostEqual(loc1.longitude, -9.1332)
                self.assertTrue(loc1.is_in_lisbon_bounds)
                self.assertEqual(loc1.postcode, "1000-223")
                self.assertEqual(mock_urlopen.call_count, 1)

            # Confirma que cache foi gravada em disco
            self.assertTrue(cache_file.is_file())

            # Segunda chamada: deve vir estritamente da cache sem qualquer chamada de rede
            with patch("urllib.request.urlopen") as mock_urlopen_2:
                loc2 = geocoder.geocode("Av. Padre Manuel da Nóbrega 4A, Lisboa")
                self.assertIsNotNone(loc2)
                self.assertEqual(loc1, loc2)
                self.assertEqual(mock_urlopen_2.call_count, 0)

    def test_validate_store_in_lisbon_heuristic_and_geocoded(self):
        """Testa validação de moradas de lojas."""
        # Heurística textual (sem geocoder)
        self.assertTrue(validate_store_in_lisbon("Av. de Roma 12, 1000-265 Lisboa"))
        self.assertTrue(validate_store_in_lisbon("Estrada de Benfica 397A, 1500-077"))
        self.assertFalse(validate_store_in_lisbon("Rua de Santa Catarina 50, 4000-442 Porto"))

        # Validação com geocoder
        geocoder = NominatimGeocoder(request_delay=0.0)
        with patch.object(
            geocoder,
            "geocode",
            return_value=GeocodedLocation(
                query="Rua Ferreira Borges 88, Lisboa",
                latitude=38.718,
                longitude=-9.162,
                display_name="Campo de Ourique, Lisboa",
                is_in_lisbon_bounds=True,
            ),
        ):
            self.assertTrue(validate_store_in_lisbon("Rua Ferreira Borges 88", geocoder))

        with patch.object(
            geocoder,
            "geocode",
            return_value=GeocodedLocation(
                query="Almada Forum",
                latitude=38.660,
                longitude=-9.175,
                display_name="Almada, Setúbal",
                is_in_lisbon_bounds=False,
            ),
        ):
            self.assertFalse(validate_store_in_lisbon("Almada Forum", geocoder))


if __name__ == "__main__":
    unittest.main()
