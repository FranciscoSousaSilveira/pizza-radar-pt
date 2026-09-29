"""Adaptador de recolha de promoções para a Telepizza Portugal (Lisboa).

Implementa PromoAdapterInterface com extração de cartões HTML (.offer-tile__wrap):
  - fetch_raw(): GET HTTP isolado para a página pública https://www.telepizza.pt/promocoes.
  - parse(): extração determinística tolerante à ordem de atributos via html.parser.HTMLParser.
  - adapt(): normalização para UnifiedPromo com preços em Decimal e cêntimos inteiros.

Regras estritas:
  - Zero presunção de StoreScope.NATIONAL: usa StoreScope.UNKNOWN porque a página pública
    não comprova a lista de lojas participantes ou exclusões no concelho de Lisboa.
  - Não assume canais (delivery/takeaway) por omissão sem evidência na fonte.
  - Campos obrigatórios ausentes originam ParseError explícito.
"""

from __future__ import annotations

import html
import http.client
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser
from typing import Any

logger = logging.getLogger(__name__)

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

_URL = "https://www.telepizza.pt/promocoes"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "close",
}

_PRICE_REGEX = re.compile(r"(\d+(?:[.,]\d{1,2})?)\s*(?:€|&euro;|euros)", re.IGNORECASE)


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


class TelepizzaHTMLParser(HTMLParser):
    """Parser HTML tolerante para extrair cartões promocionais da Telepizza.

    Imune a permutações na ordem dos atributos HTML (ex.: data-id antes ou depois de data-name).
    """

    def __init__(self) -> None:
        super().__init__()
        self.cards: list[dict[str, Any]] = []
        self._current_tab_content: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        classes = attr_dict.get("class", "").split()

        # O contentor do cartão guarda o canal ativo na tab (delivery, takeaway)
        if "offer-tile__wrap" in classes:
            self._current_tab_content = attr_dict.get("data-tab-content", "")

        # O elemento detalhado (botão ou link de detalhes) contém os metadados da oferta
        if "data-id" in attr_dict:
            card_id = attr_dict.get("data-id", "").strip()
            name = attr_dict.get("data-name", "")
            detail = attr_dict.get("data-detail", "")
            img_url = attr_dict.get("data-img-url", "").strip() or None
            tab_content = attr_dict.get("data-tab-content", "") or self._current_tab_content

            self.cards.append({
                "id": card_id,
                "name": name,
                "detail": detail,
                "img_url": img_url,
                "tab_content": tab_content,
                "attrs": attr_dict,
            })


class TelepizzaAdapter(PromoAdapterInterface):
    """Adaptador para a Telepizza Portugal com suporte a retries defensivos."""

    DEFAULT_TIMEOUT: float = 20.0

    @property
    def vendor(self) -> Brand:
        return Brand.TELEPIZZA

    def fetch_raw(self, timeout: float = DEFAULT_TIMEOUT, max_retries: int = 3) -> str:
        """Obtém o conteúdo HTML da página pública de promoções da Telepizza com retries determinísticos."""
        req = urllib.request.Request(_URL, headers=_HEADERS, method="GET")
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = resp.read()
                return body.decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                raise NetworkError(f"HTTP {exc.code} ao aceder a {_URL}: {exc.reason}", vendor=self.vendor) from exc
            except (
                http.client.RemoteDisconnected,
                ConnectionResetError,
                urllib.error.URLError,
                TimeoutError,
                OSError,
            ) as exc:
                last_exc = exc
                logger.warning(
                    "Tentativa %d/%d de recolha da Telepizza falhou: %s",
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt < max_retries:
                    time.sleep(attempt * 1.5)

        raise NetworkError(
            f"Falha após {max_retries} tentativas ao aceder a {_URL}: {last_exc}",
            vendor=self.vendor,
        ) from last_exc

    def parse(self, raw_html: str) -> list[dict[str, Any]]:
        """Extrai os cartões promocionais do HTML usando TelepizzaHTMLParser com resiliência por item."""
        if not isinstance(raw_html, str):
            raise ParseError("Payload bruto de Telepizza não é texto HTML", vendor=self.vendor)

        parser = TelepizzaHTMLParser()
        try:
            parser.feed(raw_html)
        except Exception as exc:
            raise ParseError(f"Falha de parsing HTML na Telepizza: {exc}", vendor=self.vendor) from exc

        if not parser.cards:
            raise ParseError("Nenhum cartão promocional encontrado no HTML da Telepizza", vendor=self.vendor)

        parsed: list[dict[str, Any]] = []
        for card in parser.cards:
            card_id = card.get("id")
            raw_name = card.get("name") or ""
            raw_detail = card.get("detail") or ""
            img_url = card.get("img_url")
            tab_content = card.get("tab_content") or ""

            if not card_id or not raw_name.strip():
                logger.warning("Cartão da Telepizza ignorado: id ou nome ausentes (id=%r)", card_id)
                continue

            clean_name = html.unescape(raw_name).strip()
            clean_detail = html.unescape(raw_detail).strip()

            tab_lower = tab_content.lower()
            text_lower = f"{clean_name} {clean_detail}".lower()
            channels: list[str] = []

            has_delivery = "delivery" in tab_lower or "entrega" in text_lower or "domicílio" in text_lower or "domicilio" in text_lower
            has_takeaway = "takeaway" in tab_lower or "take_away" in tab_lower or "balcão" in text_lower or "balcao" in text_lower or "levantamento" in text_lower

            if has_delivery:
                channels.append("delivery")
            if has_takeaway:
                channels.append("takeaway")

            if not channels:
                logger.warning("Oferta %s da Telepizza ignorada: sem canal comprovado", card_id)
                continue

            price_cents = _extract_cents_from_text(clean_name) or _extract_cents_from_text(clean_detail)

            parsed.append({
                "id": str(card_id),
                "title": clean_name,
                "description": clean_detail,
                "price_cents": price_cents,
                "channels": channels,
                "image_url": img_url,
                "store_scope": StoreScope.UNKNOWN,
                "store_ids": [],
                "store_names": [],
            })

        if parser.cards and not parsed:
            raise ParseError("Nenhum cartão válido da Telepizza pôde ser extraído do HTML", vendor=self.vendor)

        return parsed

    def adapt(
        self,
        item: dict[str, Any],
        observed_at: datetime,
        channel: str = "delivery",
    ) -> UnifiedPromo:
        """Normaliza um item da Telepizza para UnifiedPromo."""
        if observed_at.tzinfo is None:
            raise ValueError(f"observed_at deve ser timezone-aware, recebido: {observed_at!r}")

        dispatch_method = DispatchMethod.DELIVERY if channel == "delivery" else DispatchMethod.TAKE_AWAY
        canonical_id = f"tp_{item['id']}_{channel}"

        # Deteção de dias temáticos como Terça Louca
        days_of_week: list[Weekday] = []
        title_lower = item["title"].lower()
        if "terça" in title_lower or "terca" in title_lower:
            days_of_week = [Weekday.TUESDAY]
        elif "quinta" in title_lower:
            days_of_week = [Weekday.THURSDAY]

        discount_type = DiscountType.X_FOR_Y if "2x1" in title_lower else DiscountType.SPECIAL_MENU

        image_url = item.get("image_url")
        if image_url and not image_url.startswith(("http://", "https://")):
            image_url = None

        # StoreScope é explicitamente UNKNOWN porque a página pública não comprova
        # a lista de lojas participantes no concelho de Lisboa
        store_scope = item.get("store_scope", StoreScope.UNKNOWN)
        store_ids = item.get("store_ids", [])
        store_names = item.get("store_names", [])

        return UnifiedPromo(
            id=canonical_id,
            vendor=Brand.TELEPIZZA,
            title=item["title"],
            description=item["description"],
            observed_at=observed_at.isoformat(),
            price_cents=item["price_cents"],
            discount_type=discount_type,
            conditions=item["description"],
            days_of_week=days_of_week,
            dispatch_methods=[dispatch_method],
            store_scope=store_scope,
            store_ids=store_ids,
            store_names=store_names,
            pizza_count=None,
            pizza_size=PizzaSize.UNKNOWN,
            included_items=[],
            image_url=image_url,
            source_url=_URL,
            location_scope="Lisboa",
        )

    def fetch_promotions(self, timeout: float = DEFAULT_TIMEOUT) -> list[UnifiedPromo]:
        """Recolhe todas as promoções da página da Telepizza."""
        observed_at = datetime.now(tz=timezone.utc)
        raw_html = self.fetch_raw(timeout=timeout)
        parsed = self.parse(raw_html)

        promos: list[UnifiedPromo] = []
        seen_ids: set[str] = set()

        for it in parsed:
            for ch in it["channels"]:
                promo = self.adapt(it, observed_at, channel=ch)
                if promo.id not in seen_ids:
                    seen_ids.add(promo.id)
                    promos.append(promo)

        return self.validate_and_filter(promos)
