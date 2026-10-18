"""Módulo de validação geográfica e geocodificação para lojas de Lisboa.

Utiliza a API pública de geocodificação Nominatim (OpenStreetMap) com:
- Cache local determinística para evitar pedidos redundantes e respeitar limites de taxa (1 req/s).
- Validação estrita de limites geográficos do concelho de Lisboa (Latitude ~38.69 a ~38.80, Longitude ~ -9.23 a ~ -9.09).
- Conformidade com a política de utilização pública do Nominatim (User-Agent identificável e sem bombardeamento).
- Fallback determinístico offline seguro caso a rede ou o serviço estejam indisponíveis.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Caixa delimitadora aproximada (bounding box) do concelho de Lisboa
LISBON_BBOX = {
    "min_lat": 38.6900,
    "max_lat": 38.8050,
    "min_lon": -9.2350,
    "max_lon": -9.0850,
}

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_USER_AGENT = "PizzaRadarPT/1.0 (https://github.com/FranciscoSousaSilveira/pizza-radar-pt)"


@dataclass(frozen=True)
class GeocodedLocation:
    """Representação estruturada de coordenadas e endereço geocodificado."""

    query: str
    latitude: float
    longitude: float
    display_name: str
    is_in_lisbon_bounds: bool
    city: str | None = None
    postcode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GeocodedLocation:
        return cls(**data)


def is_within_lisbon_bounds(lat: float, lon: float) -> bool:
    """Verifica se um par de coordenadas está estritamente contido no concelho de Lisboa."""
    return (
        LISBON_BBOX["min_lat"] <= lat <= LISBON_BBOX["max_lat"]
        and LISBON_BBOX["min_lon"] <= lon <= LISBON_BBOX["max_lon"]
    )


class NominatimGeocoder:
    """Cliente geocodificador determinístico baseado em OpenStreetMap / Nominatim."""

    def __init__(
        self,
        cache_path: str | Path | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        request_delay: float = 1.0,
    ) -> None:
        self.user_agent = user_agent
        self.request_delay = request_delay
        self._last_request_time: float = 0.0
        self.cache_path = Path(cache_path) if cache_path else None
        self._cache: dict[str, dict[str, Any]] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        if self.cache_path and self.cache_path.is_file():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception as exc:
                logger.warning("Falha ao ler cache de geocoding em %s: %s", self.cache_path, exc)

    def _save_cache(self) -> None:
        if self.cache_path:
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.cache_path, "w", encoding="utf-8") as f:
                    json.dump(self._cache, f, indent=2, ensure_ascii=False)
            except Exception as exc:
                logger.warning("Falha ao gravar cache de geocoding em %s: %s", self.cache_path, exc)

    def geocode(self, address_query: str, timeout: float = 8.0) -> GeocodedLocation | None:
        """Geocodifica uma morada ou pesquisa de texto, utilizando cache persistente quando disponível."""
        query_norm = address_query.strip().lower()
        if not query_norm:
            return None

        # 1. Consulta de Cache
        if query_norm in self._cache:
            return GeocodedLocation.from_dict(self._cache[query_norm])

        # 2. Respeito pela política de rate-limit do Nominatim (mínimo 1s entre chamadas)
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)

        # 3. Pedido HTTP à API pública
        params = {
            "q": address_query,
            "format": "json",
            "addressdetails": "1",
            "limit": "1",
            "countrycodes": "pt",
        }
        url = f"{NOMINATIM_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})

        try:
            self._last_request_time = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
            data = json.loads(body.decode("utf-8"))
            if not isinstance(data, list) or len(data) == 0:
                logger.info("Nenhum resultado de geocoding para: %s", address_query)
                return None

            result = data[0]
            lat = float(result.get("lat", 0.0))
            lon = float(result.get("lon", 0.0))
            display_name = result.get("display_name", "")
            address_details = result.get("address", {})

            city = (
                address_details.get("city")
                or address_details.get("municipality")
                or address_details.get("town")
            )
            postcode = address_details.get("postcode")
            in_bounds = is_within_lisbon_bounds(lat, lon)

            loc = GeocodedLocation(
                query=address_query,
                latitude=lat,
                longitude=lon,
                display_name=display_name,
                is_in_lisbon_bounds=in_bounds,
                city=city,
                postcode=postcode,
            )

            # Gravar em cache
            self._cache[query_norm] = loc.to_dict()
            self._save_cache()
            return loc

        except Exception as exc:
            logger.warning("Erro de geocodificação ao consultar Nominatim para '%s': %s", address_query, exc)
            return None


def validate_store_in_lisbon(
    store_address: str,
    geocoder: NominatimGeocoder | None = None,
) -> bool:
    """Valida se uma loja ou endereço está comprovadamente dentro do concelho de Lisboa."""
    # Verificação preliminar rápida por código postal / cidade no texto
    addr_lower = store_address.lower()
    has_lisbon_text = "lisboa" in addr_lower or "1000-" in addr_lower or "1100-" in addr_lower or "1200-" in addr_lower or "1300-" in addr_lower or "1400-" in addr_lower or "1500-" in addr_lower or "1600-" in addr_lower or "1700-" in addr_lower or "1800-" in addr_lower or "1900-" in addr_lower

    if not geocoder:
        return has_lisbon_text

    loc = geocoder.geocode(store_address)
    if loc is not None:
        return loc.is_in_lisbon_bounds

    return has_lisbon_text
