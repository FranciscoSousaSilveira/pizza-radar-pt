"""Adaptador de recolha de promoções para a Pizza Hut Portugal (Lisboa).

Implementa PromoAdapterInterface com consumo da API REST pública do WordPress:
  - fetch_raw(): GET HTTP para https://www.pizzahut.pt/wp-json/wp/v2/ofertas?per_page=100.
  - parse(): extração determinística de ofertas do array JSON.
  - adapt(): normalização para UnifiedPromo com preços em Decimal e cêntimos inteiros.

Regras estritas:
  - Zero presunção de StoreScope.NATIONAL: usa StoreScope.UNKNOWN quando as lojas aderentes
    não estão comprovadas na resposta.
  - Deteção determinística de canais (Take Away via slug '-tw' ou termos de balcão;
    Delivery via slug '-dlv' ou termos de entrega; Dine-in via slug '-ei' ou rodízio/buffet).
  - Nunca assume entrega e takeaway em simultâneo sem evidência na fonte.
  - Campos obrigatórios ausentes ou inválidos emitem ParseError explícito.
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
from pizza_radar.core.classifier import classify_offer_type
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


def _detect_channels(slug: str, title: str, description: str) -> list[DispatchMethod]:
    """Extrai os canais de distribuição com base estrita em evidência no slug e texto."""
    slug_lower = slug.lower()
    text_lower = f"{title} {description}".lower()

    methods: list[DispatchMethod] = []

    # Take Away / Balcão
    is_takeaway = (
        slug_lower.endswith("-tw")
        or "-tw-" in slug_lower
        or "takeaway" in slug_lower
        or "balcão" in text_lower
        or "balcao" in text_lower
        or "takeaway" in text_lower
        or "take-away" in text_lower
        or "levantamento" in text_lower
    )
    if is_takeaway:
        methods.append(DispatchMethod.TAKE_AWAY)

    # Delivery / Domicílio
    is_delivery = (
        slug_lower.endswith("-dlv")
        or slug_lower.endswith("-dl")
        or "-dlv-" in slug_lower
        or "-dl-" in slug_lower
        or "delivery" in slug_lower
        or "domicílio" in text_lower
        or "domicilio" in text_lower
        or "entrega" in text_lower
    )
    if is_delivery:
        methods.append(DispatchMethod.DELIVERY)

    # Dine-In / Restaurante / Sala
    is_dine_in = (
        slug_lower.endswith("-ei")
        or "-ei-" in slug_lower
        or "rodizio" in slug_lower
        or "buffet" in slug_lower
        or "sala" in text_lower
        or "restaurante" in text_lower
        or "rodízio" in text_lower
        or "buffet" in text_lower
    )
    if is_dine_in and DispatchMethod.DINE_IN not in methods:
        methods.append(DispatchMethod.DINE_IN)

    return methods


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
        """Extrai os campos de cada oferta com validação rigorosa de campos obrigatórios e canais."""
        if not isinstance(raw, list):
            raise ParseError("Array de ofertas bruto da Pizza Hut inválido", vendor=self.vendor)

        parsed: list[dict[str, Any]] = []
        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                raise ParseError(f"Item {idx} de ofertas da Pizza Hut não é um objeto válido", vendor=self.vendor)

            item_id = item.get("id")
            title_obj = item.get("title")
            title_rendered = title_obj.get("rendered") if isinstance(title_obj, dict) else None

            if item_id is None or not title_rendered or str(title_rendered).strip() == "":
                raise ParseError(
                    f"Item {idx} da Pizza Hut com campos obrigatórios em falta (id={item_id!r}, title={title_rendered!r})",
                    vendor=self.vendor,
                )

            clean_title = html.unescape(str(title_rendered)).strip()
            slug = str(item.get("slug") or item_id)
            desc = ""
            yoast = item.get("yoast_head_json")
            if isinstance(yoast, dict):
                desc = str(yoast.get("description") or "").strip()

            price_cents = _extract_cents_from_text(clean_title) or _extract_cents_from_text(desc)
            link = str(item.get("link") or "https://www.pizzahut.pt/ofertas/")

            # Extração de lojas participantes caso existam no payload
            store_ids: list[str] = []
            store_names: list[str] = []
            if "participating_stores" in item and isinstance(item["participating_stores"], list):
                for st in item["participating_stores"]:
                    if isinstance(st, dict):
                        if "id" in st:
                            store_ids.append(str(st["id"]))
                        if "name" in st:
                            store_names.append(str(st["name"]))
                    elif isinstance(st, str):
                        store_ids.append(st)
                        store_names.append(st)

            store_scope = StoreScope.SPECIFIC_STORES if store_ids else StoreScope.UNKNOWN

            # Deteção de canais de atendimento
            channels = _detect_channels(slug, clean_title, desc)
            if not channels:
                if "dispatch_methods" in item and isinstance(item["dispatch_methods"], list):
                    channels = [
                        DispatchMethod(m) if isinstance(m, str) else m
                        for m in item["dispatch_methods"]
                    ]
                else:
                    raise ParseError(
                        f"Oferta {item_id} ({slug}) da Pizza Hut não possui canal de distribuição comprovado",
                        vendor=self.vendor,
                    )

            parsed.append({
                "id": str(item_id),
                "slug": slug,
                "title": clean_title,
                "description": desc,
                "price_cents": price_cents,
                "link": link,
                "store_scope": store_scope,
                "store_ids": store_ids,
                "store_names": store_names,
                "dispatch_methods": channels,
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
        elif "segunda" in title_lower:
            days_of_week = [Weekday.MONDAY]
        elif "quarta" in title_lower:
            days_of_week = [Weekday.WEDNESDAY]

        store_scope = item.get("store_scope", StoreScope.UNKNOWN)
        store_ids = item.get("store_ids", [])
        store_names = item.get("store_names", [])
        dispatch_methods = item.get("dispatch_methods", [DispatchMethod.TAKE_AWAY])

        offer_type = classify_offer_type(
            title=item["title"],
            description=item["description"],
            included_items=[],
            pizza_count=None,
        )

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
            store_scope=store_scope,
            store_ids=store_ids,
            store_names=store_names,
            pizza_count=None,
            pizza_size=PizzaSize.UNKNOWN,
            included_items=[],
            source_url=item["link"],
            location_scope="Lisboa",
            offer_type=offer_type,
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
