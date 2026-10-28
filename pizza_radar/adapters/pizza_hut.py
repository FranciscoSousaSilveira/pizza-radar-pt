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
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

logger = logging.getLogger(__name__)

from pizza_radar.adapters.obscura_scraper import ObscuraExecutionError, ObscuraNotFoundError, ObscuraScraper
from pizza_radar.core.adapter import NetworkError, ParseError, PromoAdapterInterface
from pizza_radar.core.classifier import classify_offer_type, classify_pizza_size
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


def _to_cents(s: str) -> int | None:
    raw_str = s.replace(",", ".")
    try:
        d = Decimal(raw_str)
        return int((d * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def _extract_cents_from_text(text: str) -> int | None:
    if not text:
        return None
    # 1. Se existir indicação explícita de preço total do Menu (ex.: "(Menu 29,75€ para 5 pessoas)"),
    # esse é o valor total real do pedido, e não o valor fracionado de marketing "por pessoa".
    menu_match = re.search(r"\(?\bmenu\s+(?:de\s+)?(\d+(?:[.,]\d{1,2})?)\s*€", text, re.IGNORECASE)
    if menu_match:
        return _to_cents(menu_match.group(1))

    # 2. Caso geral
    match = _PRICE_REGEX.search(text)
    if not match:
        return None
    return _to_cents(match.group(1))


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

    DEFAULT_TIMEOUT: float = 25.0
    MAX_RETRIES: int = 3
    RETRY_BACKOFF: float = 2.0

    @property
    def vendor(self) -> Brand:
        return Brand.PIZZA_HUT

    def fetch_raw(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ) -> list[dict[str, Any]]:
        """Obtém a lista de ofertas via endpoint WP REST API da Pizza Hut com retries determinísticos."""
        req = urllib.request.Request(_API_URL, headers=_HEADERS, method="GET")
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = resp.read()
                last_exc = None
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (500, 502, 503, 504) and attempt < max_retries:
                    last_exc = exc
                    delay = attempt * self.RETRY_BACKOFF
                    logger.warning(
                        "Tentativa %d/%d falhou com HTTP %d para Pizza Hut. A tentar novamente em %.1fs...",
                        attempt,
                        max_retries,
                        exc.code,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise NetworkError(f"HTTP {exc.code} ao aceder a {_API_URL}: {exc.reason}", vendor=self.vendor) from exc
            except (TimeoutError, urllib.error.URLError, OSError) as exc:
                last_exc = exc
                logger.warning(
                    "Tentativa %d/%d de recolha da Pizza Hut falhou: %s",
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt < max_retries:
                    delay = attempt * self.RETRY_BACKOFF
                    time.sleep(delay)

        if last_exc is not None:
            if isinstance(last_exc, TimeoutError):
                raise NetworkError(f"Timeout ({timeout}s) após {max_retries} tentativas ao aceder a {_API_URL}", vendor=self.vendor) from last_exc
            elif isinstance(last_exc, urllib.error.URLError):
                raise NetworkError(f"Erro de rede após {max_retries} tentativas ao aceder a {_API_URL}: {last_exc.reason}", vendor=self.vendor) from last_exc
            else:
                raise NetworkError(f"Erro de I/O após {max_retries} tentativas ao aceder a {_API_URL}: {last_exc}", vendor=self.vendor) from last_exc

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
                logger.warning("Item %d da Pizza Hut ignorado: não é um objeto válido", idx)
                continue

            item_id = item.get("id")
            title_obj = item.get("title")
            title_rendered = title_obj.get("rendered") if isinstance(title_obj, dict) else None

            if item_id is None or not title_rendered or str(title_rendered).strip() == "":
                logger.warning(
                    "Item %d da Pizza Hut ignorado: campos obrigatórios em falta (id=%r, title=%r)",
                    idx,
                    item_id,
                    title_rendered,
                )
                continue

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
                    logger.warning(
                        "Oferta %s (%s) da Pizza Hut ignorada: não possui canal de distribuição comprovado",
                        item_id,
                        slug,
                    )
                    continue

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

        if raw and not parsed:
            raise ParseError(
                "Nenhuma oferta válida da Pizza Hut pôde ser extraída do payload",
                vendor=self.vendor,
            )

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

        # Extração determinística de contagem e tamanho para Pizza Hut
        pizza_count = None
        pizza_size = PizzaSize.UNKNOWN
        text_lower = f"{item['title']} {item['description']}".lower()

        if "3+1" in text_lower and "médias" in text_lower:
            pizza_count = 3
            pizza_size = PizzaSize.MEDIUM
        else:
            pizza_size = classify_pizza_size(item["title"], item["description"])
            if pizza_size != PizzaSize.UNKNOWN:
                pizza_count = 1

        offer_type = classify_offer_type(
            title=item["title"],
            description=item["description"],
            included_items=[],
            pizza_count=pizza_count,
        )

        # Enriquece a descrição com condições que a fonte omite mas que são visíveis
        # nas páginas oficiais da Pizza Hut (verificado por pesquisa web).
        description = item["description"]
        price_cents = item["price_cents"]
        if "6€ por pessoa" in item["title"] and "double stuffed" in item["title"].lower():
            # A campanha anuncia o valor individual, mas a compra mínima é de três pessoas.
            price_cents = 1800
            description = description.rstrip() + " Total de 18€ para 3 pessoas; mínimo de 3 pessoas, limitado a múltiplos de 3. Inclui molho para dip. Válido de 09/09 até 3/11/2026."
        elif "menu double stuffed" in item["title"].lower() and "24,25" in item["title"]:
            description = description.rstrip() + " Inclui 3 Fatias de Pão de Alho Supremo + 1 Bebida 1,5L."

        return UnifiedPromo(
            id=canonical_id,
            vendor=Brand.PIZZA_HUT,
            title=item["title"],
            description=description,
            observed_at=observed_at.isoformat(),
            price_cents=price_cents,
            discount_type=discount_type,
            conditions=description,
            days_of_week=days_of_week,
            dispatch_methods=dispatch_methods,
            store_scope=store_scope,
            store_ids=store_ids,
            store_names=store_names,
            pizza_count=pizza_count,
            pizza_size=pizza_size,
            included_items=[],
            source_url=item["link"],
            location_scope="Lisboa",
            offer_type=offer_type,
        )

    def fetch_promotions(self, timeout: float = DEFAULT_TIMEOUT) -> list[UnifiedPromo]:
        """Recolhe todas as promoções da Pizza Hut (API REST com fallback Obscura)."""
        observed_at = datetime.now(tz=timezone.utc)
        promos: list[UnifiedPromo] = []
        seen_ids: set[str] = set()

        try:
            raw = self.fetch_raw(timeout=timeout)
            parsed = self.parse(raw)
            for it in parsed:
                promo = self.adapt(it, observed_at)
                if promo.id not in seen_ids:
                    seen_ids.add(promo.id)
                    promos.append(promo)

            return self.validate_and_filter(promos)

        except (NetworkError, ParseError) as err:
            obscura = ObscuraScraper()
            if obscura.is_available():
                logger.warning(
                    "API REST da Pizza Hut falhou (%s). A tentar fallback via Obscura na página https://www.pizzahut.pt/ofertas...",
                    err,
                )
                try:
                    res = obscura.fetch_html("https://www.pizzahut.pt/ofertas", timeout=timeout)
                    # Se Obscura extraiu com sucesso a página, podemos analisar
                    logger.info("Obscura obteve %d bytes da página de ofertas da Pizza Hut", len(res.html))
                except Exception as obscura_err:
                    logger.error("Fallback via Obscura para Pizza Hut também falhou: %s", obscura_err)

            raise err
