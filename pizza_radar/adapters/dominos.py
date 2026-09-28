"""Adaptador de recolha de promoções para a Domino's Pizza Portugal (Lisboa).

Implementa PromoAdapterInterface com separação de camadas:
  - fetch_raw(): POST HTTP isolado para a API ajax/order.php da Domino's.
  - parse(): extração determinística de combos do payload JSON.
  - adapt(): normalização para UnifiedPromo com preços em Decimal e cêntimos inteiros.

Regras estritas:
  - Zero IA em runtime.
  - Zero segredos.
  - Preços em integer cents calculados via Decimal (sem float).
  - Nunca inventa composição de pizzas ou preços.
  - Falhas isoladas em NetworkError e ParseError.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
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

_AJAX_URL = "https://www.dominospizza.pt/ajax/order.php"
_STORE_ID_LISBOA = "140"  # Areeiro / Lisboa Centro

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "*/*",
}

_PRICE_REGEX = re.compile(r"(\d+(?:[.,]\d{1,2})?)\s*€")
_DISCOUNT_REGEX = re.compile(r"(\d+)\s*%\s*DESCONTO", re.IGNORECASE)


def _extract_cents_from_text(text: str) -> int | None:
    """Extrai valor em euros via regex e converte diretamente para cêntimos via Decimal."""
    match = _PRICE_REGEX.search(text)
    if not match:
        return None
    raw_str = match.group(1).replace(",", ".")
    try:
        d = Decimal(raw_str)
        return int((d * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def _extract_discount_percentage(text: str) -> float | None:
    match = _DISCOUNT_REGEX.search(text)
    if match:
        return float(match.group(1))
    return None


class DominosAdapter(PromoAdapterInterface):
    """Adaptador para a Domino's Pizza Portugal."""

    DEFAULT_TIMEOUT: float = 15.0

    @property
    def vendor(self) -> Brand:
        return Brand.DOMINOS

    def fetch_raw(
        self,
        delivery_method: str = "D",
        store_id: str = _STORE_ID_LISBOA,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        """Efetua pedido POST ao endpoint ajax/order.php da Domino's."""
        data = urllib.parse.urlencode({
            "get_menu": store_id,
            "time": "NOW",
            "delivery_method": delivery_method,
        }).encode("utf-8")

        req = urllib.request.Request(_AJAX_URL, data=data, headers=_HEADERS, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            raise NetworkError(f"HTTP {exc.code} ao aceder a {_AJAX_URL}: {exc.reason}", vendor=self.vendor) from exc
        except urllib.error.URLError as exc:
            raise NetworkError(f"Erro de rede ao aceder a {_AJAX_URL}: {exc.reason}", vendor=self.vendor) from exc
        except TimeoutError as exc:
            raise NetworkError(f"Timeout ({timeout}s) ao aceder a {_AJAX_URL}", vendor=self.vendor) from exc
        except OSError as exc:
            raise NetworkError(f"Erro de I/O ao aceder a {_AJAX_URL}: {exc}", vendor=self.vendor) from exc

        try:
            # parsing nativo Decimal para números de vírgula flutuante
            parsed_json = json.loads(body.decode("utf-8"), parse_float=Decimal)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ParseError(f"Resposta de {_AJAX_URL} não é JSON válido: {exc}", vendor=self.vendor) from exc

        if not isinstance(parsed_json, dict) or "combos" not in parsed_json:
            raise ParseError(f"Estrutura inesperada na resposta da Domino's: falta chave 'combos'", vendor=self.vendor)

        return parsed_json

    def parse(
        self,
        raw: dict[str, Any],
        delivery_method: str = "D",
    ) -> list[dict[str, Any]]:
        """Extrai a lista de combos de forma determinística."""
        combos_data = raw.get("combos", {}).get("data", [])
        if not isinstance(combos_data, list):
            raise ParseError("Chave 'combos.data' não é uma lista", vendor=self.vendor)

        parsed: list[dict[str, Any]] = []
        for idx, item in enumerate(combos_data):
            if not isinstance(item, dict):
                continue
            combo_id = item.get("id")
            title = item.get("title")
            if not combo_id or not title:
                continue

            clean_title = html.unescape(str(title)).strip()
            clean_desc = html.unescape(str(item.get("description") or "")).strip()

            price_cents = _extract_cents_from_text(clean_title) or _extract_cents_from_text(clean_desc)
            discount_pct = _extract_discount_percentage(clean_title) or _extract_discount_percentage(clean_desc)

            parsed.append({
                "id": str(combo_id),
                "title": clean_title,
                "description": clean_desc,
                "price_cents": price_cents,
                "discount_percentage": discount_pct,
                "delivery_method": delivery_method,
                "terms": item.get("terms") or "",
                "image_url": item.get("image_url"),
            })
        return parsed

    def adapt(
        self,
        item: dict[str, Any],
        observed_at: datetime,
    ) -> UnifiedPromo:
        """Converte item parseado para UnifiedPromo."""
        if observed_at.tzinfo is None:
            raise ValueError(f"observed_at deve ser timezone-aware, recebido: {observed_at!r}")

        is_delivery = item["delivery_method"] == "D"
        dispatch_method = DispatchMethod.DELIVERY if is_delivery else DispatchMethod.TAKE_AWAY
        canonical_id = f"dom_{item['id']}_{'delivery' if is_delivery else 'takeaway'}"

        discount_type = DiscountType.PERCENTAGE if item.get("discount_percentage") else DiscountType.SPECIAL_MENU

        # Deteção de dias da semana em promoções semanais conhecidas (ex: Segundas a Dobrar)
        days_of_week: list[Weekday] = []
        if "segunda" in item["title"].lower() or "segunda" in item["description"].lower():
            days_of_week = [Weekday.MONDAY]

        image_url = item.get("image_url")
        if image_url and not str(image_url).startswith(("http://", "https://")):
            image_url = None

        return UnifiedPromo(
            id=canonical_id,
            vendor=Brand.DOMINOS,
            title=item["title"],
            description=item["description"],
            observed_at=observed_at.isoformat(),
            price_cents=item["price_cents"],
            discount_type=discount_type,
            discount_percentage=item.get("discount_percentage"),
            conditions=item.get("terms", ""),
            days_of_week=days_of_week,
            dispatch_methods=[dispatch_method],
            store_scope=StoreScope.SPECIFIC_STORES,
            store_ids=[_STORE_ID_LISBOA],
            store_names=["Areeiro (Lisboa)"],
            pizza_count=None,
            pizza_size=PizzaSize.UNKNOWN,
            included_items=[],
            image_url=image_url,
            source_url="https://www.dominospizza.pt/promocoes",
            location_scope="Lisboa",
        )

    def fetch_promotions(self, timeout: float = DEFAULT_TIMEOUT) -> list[UnifiedPromo]:
        """Recolhe promoções da Domino's para Delivery e Take Away."""
        observed_at = datetime.now(tz=timezone.utc)
        promos: list[UnifiedPromo] = []
        seen_ids: set[str] = set()

        for method in ("D", "C"):
            raw = self.fetch_raw(delivery_method=method, timeout=timeout)
            parsed = self.parse(raw, delivery_method=method)
            for it in parsed:
                promo = self.adapt(it, observed_at)
                if promo.id not in seen_ids:
                    seen_ids.add(promo.id)
                    promos.append(promo)

        return self.validate_and_filter(promos)
