"""Adaptador de recolha de promoções para a Telepizza Portugal (Lisboa).

Implementa PromoAdapterInterface com extração de cartões HTML (.offer-tile__wrap):
  - fetch_raw(): GET HTTP isolado para a página pública https://www.telepizza.pt/promocoes.
  - parse(): extração determinística via regex de atributos data-* dos cartões promocionais.
  - adapt(): normalização para UnifiedPromo com preços em Decimal e cêntimos inteiros.
"""

from __future__ import annotations

import html
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

_URL = "https://www.telepizza.pt/promocoes"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_PRICE_REGEX = re.compile(r"(\d+(?:[.,]\d{1,2})?)\s*(?:€|&euro;|euros)", re.IGNORECASE)
_CARD_REGEX = re.compile(
    r'<div[^>]*class="[^"]*offer-tile__wrap[^"]*"[^>]*data-tab-content="([^"]*)"[^>]*>.*?'
    r'<a[^>]*class="[^"]*offer-tile__view-more__btn-icon[^"]*"[^>]*'
    r'data-id="([^"]*)"[^>]*'
    r'data-name="([^"]*)"[^>]*'
    r'data-detail="([^"]*)"[^>]*'
    r'(?:data-img-url="([^"]*)")?',
    re.DOTALL | re.IGNORECASE,
)


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


class TelepizzaAdapter(PromoAdapterInterface):
    """Adaptador para a Telepizza Portugal."""

    DEFAULT_TIMEOUT: float = 15.0

    @property
    def vendor(self) -> Brand:
        return Brand.TELEPIZZA

    def fetch_raw(self, timeout: float = DEFAULT_TIMEOUT) -> str:
        """Obtém o conteúdo HTML da página pública de promoções da Telepizza."""
        req = urllib.request.Request(_URL, headers=_HEADERS, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            raise NetworkError(f"HTTP {exc.code} ao aceder a {_URL}: {exc.reason}", vendor=self.vendor) from exc
        except urllib.error.URLError as exc:
            raise NetworkError(f"Erro de rede ao aceder a {_URL}: {exc.reason}", vendor=self.vendor) from exc
        except TimeoutError as exc:
            raise NetworkError(f"Timeout ({timeout}s) ao aceder a {_URL}", vendor=self.vendor) from exc
        except OSError as exc:
            raise NetworkError(f"Erro de I/O ao aceder a {_URL}: {exc}", vendor=self.vendor) from exc

        return body.decode("utf-8", errors="replace")

    def parse(self, raw_html: str) -> list[dict[str, Any]]:
        """Extrai os cartões promocionais do HTML."""
        if not isinstance(raw_html, str):
            raise ParseError("Payload bruto de Telepizza não é texto HTML", vendor=self.vendor)

        cards = _CARD_REGEX.findall(raw_html)
        if not cards:
            # Se não encontrou cartões via regex estrita de tag <a>, tentar varredura flexível de atributos
            alt_regex = re.compile(
                r'data-id="([^"]+)"[^>]*data-name="([^"]+)"[^>]*data-detail="([^"]*)"',
                re.IGNORECASE,
            )
            simple_matches = alt_regex.findall(raw_html)
            if not simple_matches:
                raise ParseError("Nenhum cartão promocional encontrado no HTML da Telepizza", vendor=self.vendor)
            parsed_simple: list[dict[str, Any]] = []
            for m_id, m_name, m_detail in simple_matches:
                clean_name = html.unescape(m_name).strip()
                clean_detail = html.unescape(m_detail).strip()
                price_c = _extract_cents_from_text(clean_name) or _extract_cents_from_text(clean_detail)
                parsed_simple.append({
                    "id": m_id.strip(),
                    "title": clean_name,
                    "description": clean_detail,
                    "price_cents": price_c,
                    "channels": ["delivery", "takeaway"],
                    "image_url": None,
                })
            return parsed_simple

        parsed: list[dict[str, Any]] = []
        for tab_content, card_id, raw_name, raw_detail, img_url in cards:
            clean_name = html.unescape(raw_name).strip()
            clean_detail = html.unescape(raw_detail).strip()

            channels: list[str] = []
            tab_lower = tab_content.lower()
            if "delivery" in tab_lower:
                channels.append("delivery")
            if "takeaway" in tab_lower or "take_away" in tab_lower:
                channels.append("takeaway")
            if not channels:
                channels = ["delivery", "takeaway"]

            price_cents = _extract_cents_from_text(clean_name) or _extract_cents_from_text(clean_detail)

            parsed.append({
                "id": card_id.strip(),
                "title": clean_name,
                "description": clean_detail,
                "price_cents": price_cents,
                "channels": channels,
                "image_url": img_url.strip() if img_url else None,
            })
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
            store_scope=StoreScope.NATIONAL,  # Catálogo público da página nacional
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
