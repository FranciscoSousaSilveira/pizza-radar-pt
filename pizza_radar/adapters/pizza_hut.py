"""Adaptador de recolha de promoções para a Pizza Hut Portugal (Lisboa).

Implementa PromoAdapterInterface com consumo da API REST pública do WordPress:
  - fetch_raw(): GET HTTP para https://www.pizzahut.pt/wp-json/wp/v2/ofertas?per_page=100.
  - parse(): extração determinística de ofertas do array JSON.
  - adapt(): normalização para UnifiedPromo com preços em Decimal e cêntimos inteiros.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from pizza_radar.core.adapter import NetworkError, ParseError, PromoAdapterInterface
from pizza_radar.core.models import (
    Brand,
    DiscountType,
    DispatchMethod,
    PizzaSize,
    StoreScope,
    UnifiedPromo,
    Weekday,
)

_API_URL = "https://www.pizzahut.pt/wp-json/wp/v2/ofertas?per_page=100"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_PRICE_REGEX = re.compile(r"(\d+(?:[.,]\d{1,2})?)\s*€")


def _extract_cents_from_text(text: str) -> int | None:
    match = _PRICE_REGEX.search(text)
    if not match:
        return None
    raw_str = match.group(1).replace(",", ".")
    try:
        d = Decimal(raw_str)
        return int((d * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


class PizzaHutAdapter(PromoAdapterInterface):
    """Adaptador para a Pizza Hut Portugal."""

    DEFAULT_TIMEOUT: float = 15.0

    @property
    def vendor(self) -> Brand:
        return Brand.PIZZA_HUT

    def fetch_raw(self, timeout: float = DEFAULT_TIMEOUT) -> list[dict[str, Any]]:
        """Obtém a lista de ofertas via endpoint WP REST API da Pizza Hut."""
        req = urllib.request.Request(_API_URL, headers=_HEADERS, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            raise NetworkError(f"HTTP {exc.code} ao aceder a {_API_URL}: {exc.reason}", vendor=self.vendor) from exc
        except urllib.error.URLError as exc:
            raise NetworkError(f"Erro de rede ao aceder a {_API_URL}: {exc.reason}", vendor=self.vendor) from exc
        except TimeoutError as exc:
            raise NetworkError(f"Timeout ({timeout}s) ao aceder a {_API_URL}", vendor=self.vendor) from exc
        except OSError as exc:
            raise NetworkError(f"Erro de I/O ao aceder a {_API_URL}: {exc}", vendor=self.vendor) from exc

        try:
            data = json.loads(body.decode("utf-8"), parse_float=Decimal)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ParseError(f"Resposta de {_API_URL} não é JSON válido: {exc}", vendor=self.vendor) from exc

        if not isinstance(data, list):
            raise ParseError(f"Estrutura inesperada na resposta da Pizza Hut: esperada lista", vendor=self.vendor)

        return data

    def parse(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extrai os campos de cada oferta."""
        parsed: list[dict[str, Any]] = []
        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            title_rendered = item.get("title", {}).get("rendered") if isinstance(item.get("title"), dict) else None
            if not item_id or not title_rendered:
                continue

            clean_title = html.unescape(str(title_rendered)).strip()
            desc = ""
            yoast = item.get("yoast_head_json")
            if isinstance(yoast, dict):
                desc = str(yoast.get("description") or "").strip()

            price_cents = _extract_cents_from_text(clean_title) or _extract_cents_from_text(desc)
            link = str(item.get("link") or "https://www.pizzahut.pt/ofertas/")

            parsed.append({
                "id": str(item_id),
                "slug": item.get("slug") or str(item_id),
                "title": clean_title,
                "description": desc,
                "price_cents": price_cents,
                "link": link,
            })
        return parsed

    def adapt(
        self,
        item: dict[str, Any],
        observed_at: datetime,
    ) -> UnifiedPromo:
        """Normaliza um item da Pizza Hut para UnifiedPromo."""
        if observed_at.tzinfo is None:
            raise ValueError(f"observed_at deve ser timezone-aware, recebido: {observed_at!r}")

        canonical_id = f"ph_{item['id']}_promo"
        title_lower = item["title"].lower()

        discount_type = DiscountType.X_FOR_Y if ("2x1" in title_lower or "2×1" in title_lower) else DiscountType.SPECIAL_MENU

        # Deteção de dias temáticos como Terças 2x1
        days_of_week: list[Weekday] = []
        if "terça" in title_lower or "terca" in title_lower:
            days_of_week = [Weekday.TUESDAY]

        dispatch_methods = [DispatchMethod.TAKE_AWAY, DispatchMethod.DELIVERY]

        return UnifiedPromo(
            id=canonical_id,
            vendor=Brand.PIZZA_HUT,
            title=item["title"],
            description=item["description"],
            observed_at=observed_at.isoformat(),
            price_cents=item["price_cents"],
            discount_type=discount_type,
            conditions=item["description"],
            days_of_week=days_of_week,
            dispatch_methods=dispatch_methods,
            store_scope=StoreScope.NATIONAL,
            pizza_count=None,
            pizza_size=PizzaSize.UNKNOWN,
            included_items=[],
            source_url=item["link"],
            location_scope="Lisboa",
        )

    def fetch_promotions(self, timeout: float = DEFAULT_TIMEOUT) -> list[UnifiedPromo]:
        """Recolhe todas as promoções da Pizza Hut."""
        observed_at = datetime.now(tz=timezone.utc)
        raw = self.fetch_raw(timeout=timeout)
        parsed = self.parse(raw)

        promos: list[UnifiedPromo] = []
        seen_ids: set[str] = set()

        for it in parsed:
            promo = self.adapt(it, observed_at)
            if promo.id not in seen_ids:
                seen_ids.add(promo.id)
                promos.append(promo)

        return self.validate_and_filter(promos)
