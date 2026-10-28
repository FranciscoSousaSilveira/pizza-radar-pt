"""Recolha determinística das promoções Telepizza visíveis na Glovo Lisboa.

Consulta uma página pública, sem autenticação nem endpoints privados. Só são
aceites cartões que a própria página marca visualmente como promoção.
"""

from __future__ import annotations

import hashlib
import html
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

from pizza_radar.core.adapter import NetworkError, ParseError, PromoAdapterInterface
from pizza_radar.core.classifier import classify_offer_type, classify_pizza_size
from pizza_radar.core.models import (
    Brand,
    DiscountType,
    DispatchMethod,
    StoreScope,
    UnifiedPromo,
)

_STORE_URL = "https://glovoapp.com/pt/pt/lisboa/stores/telepizza-lis"
_PRICE_RE = re.compile(r"(\d+(?:[.,]\d{1,2})?)\s*€")
_PERCENT_RE = re.compile(r"-\s*(\d+(?:[.,]\d+)?)\s*%")
_PIZZA_TITLE_RE = re.compile(r"\b(pizza|m[eé]dia|grande|familiar|individual)\b", re.IGNORECASE)
_USER_AGENT = "PizzaRadarPT/1.0 (+https://pizza-radar.pt)"
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def _price_to_cents(text: str) -> int | None:
    match = _PRICE_RE.search(text)
    if not match:
        return None
    whole, _, decimal = match.group(1).replace(",", ".").partition(".")
    return int(whole) * 100 + int((decimal + "00")[:2])


def _promo_id(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
    digest = hashlib.sha256(title.casefold().encode("utf-8")).hexdigest()[:8]
    return f"glovo-{normalized[:48]}-{digest}"


class _GlovoPromotionParser(HTMLParser):
    """Lê cartões visíveis ``data-testid=product-tile`` do HTML SSR da Glovo."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.promotions: list[dict[str, str]] = []
        self._depth = 0
        self._tile: dict[str, object] | None = None
        self._promo_depths: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _VOID_TAGS:
            self._depth += 1
        attr = {key: value or "" for key, value in attrs}
        if tag == "div" and attr.get("data-testid") == "product-tile" and self._tile is None:
            self._tile = {"depth": self._depth, "title": "", "text": [], "tags": []}
            return
        if self._tile is None:
            return
        if tag == "img" and not self._tile["title"]:
            self._tile["title"] = attr.get("alt", "").strip()
        if attr.get("data-style") == "promotion":
            self._promo_depths.append(self._depth)

    def handle_data(self, data: str) -> None:
        if self._tile is None:
            return
        self._tile["text"].append(data)
        if self._promo_depths:
            self._tile["tags"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._promo_depths and self._promo_depths[-1] == self._depth:
            self._promo_depths.pop()
        if self._tile is not None and tag == "div" and self._tile["depth"] == self._depth:
            title = str(self._tile["title"])
            text = " ".join(str(part).strip() for part in self._tile["text"] if str(part).strip())
            tag_text = " ".join(str(part).strip() for part in self._tile["tags"] if str(part).strip())
            if title and tag_text and _price_to_cents(text) is not None:
                self.promotions.append({"title": title, "text": text, "tag": tag_text})
            self._tile = None
            self._promo_depths.clear()
        if tag not in _VOID_TAGS:
            self._depth = max(0, self._depth - 1)


class GlovoTelepizzaAdapter(PromoAdapterInterface):
    """Fonte pública da Glovo para promoções Telepizza disponíveis em Lisboa."""

    DEFAULT_TIMEOUT = 20.0

    def __init__(self) -> None:
        self.coverage_level = "FEATURED"
        self.coverage_note = "Promoções visíveis na Glovo para Lisboa; preço e disponibilidade dependem da morada."

    @property
    def vendor(self) -> Brand:
        return Brand.TELEPIZZA

    def fetch_raw(self, timeout: float = DEFAULT_TIMEOUT) -> str:
        request = urllib.request.Request(
            _STORE_URL,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise NetworkError(f"HTTP {exc.code} ao consultar a página Glovo Telepizza", vendor=self.vendor) from exc
        except urllib.error.URLError as exc:
            raise NetworkError(f"Erro de rede ao consultar a página Glovo Telepizza: {exc.reason}", vendor=self.vendor) from exc
        except (TimeoutError, OSError) as exc:
            raise NetworkError(f"Falha ao consultar a página Glovo Telepizza: {exc}", vendor=self.vendor) from exc

    def parse(self, raw_html: str) -> list[dict[str, object]]:
        if not isinstance(raw_html, str):
            raise ParseError("Resposta da Glovo não é HTML", vendor=self.vendor)
        if "Telepizza" not in raw_html:
            raise ParseError("A página Glovo não confirma a loja Telepizza", vendor=self.vendor)

        parser = _GlovoPromotionParser()
        try:
            parser.feed(raw_html)
        except Exception as exc:
            raise ParseError(f"Falha ao interpretar promoções visíveis da Glovo: {exc}", vendor=self.vendor) from exc

        deduplicated: dict[str, dict[str, object]] = {}
        for item in parser.promotions:
            title = html.unescape(item["title"]).strip()
            tag = html.unescape(item["tag"]).strip()
            text = html.unescape(item["text"]).strip()
            price_cents = _price_to_cents(text)
            if price_cents is None:
                continue
            percentage = _PERCENT_RE.search(tag)
            discount_percentage = float(percentage.group(1).replace(",", ".")) if percentage else None
            deduplicated.setdefault(
                title.casefold(),
                {
                    "id": _promo_id(title),
                    "title": title,
                    "description": f"{tag} — promoção observada na Glovo.",
                    "conditions": f"{tag}. Preço e disponibilidade confirmados na Glovo para Lisboa.",
                    "price_cents": price_cents,
                    "discount_percentage": discount_percentage,
                    # shortcut: títulos sem nome/tamanho de pizza não comprovam que um 2x1 é pizza; ampliar só com categoria pública.
                    "pizza_count": 2 if (
                        ("2x1" in tag.casefold() or "2 por 1" in tag.casefold())
                        and _PIZZA_TITLE_RE.search(title)
                    ) else None,
                },
            )
        if not deduplicated:
            raise ParseError("Nenhuma promoção visível da Telepizza encontrada na página Glovo", vendor=self.vendor)
        return list(deduplicated.values())

    def adapt(self, item: dict[str, object], observed_at: datetime) -> UnifiedPromo:
        title = str(item["title"])
        description = str(item["description"])
        tag = description.casefold()
        discount_type = (
            DiscountType.PERCENTAGE if item.get("discount_percentage") is not None
            else DiscountType.X_FOR_Y if "2x1" in tag or "2 por 1" in tag
            else DiscountType.SPECIAL_MENU
        )
        return UnifiedPromo(
            id=f"tp_{item['id']}_delivery",
            vendor=self.vendor,
            title=title,
            description=description,
            observed_at=observed_at.isoformat(),
            price_cents=int(item["price_cents"]),
            discount_type=discount_type,
            discount_percentage=item.get("discount_percentage"),
            conditions=str(item["conditions"]),
            dispatch_methods=[DispatchMethod.DELIVERY],
            # A página confirma Lisboa, não uma loja física individual.
            store_scope=StoreScope.UNKNOWN,
            pizza_count=item.get("pizza_count"),
            pizza_size=classify_pizza_size(title, description),
            included_items=[],
            source_url=_STORE_URL,
            location_scope="Lisboa",
            offer_type=classify_offer_type(title, description, [], item.get("pizza_count")),
        )

    def fetch_promotions(self, timeout: float = DEFAULT_TIMEOUT) -> list[UnifiedPromo]:
        observed_at = datetime.now(timezone.utc)
        promos = [self.adapt(item, observed_at) for item in self.parse(self.fetch_raw(timeout))]
        return self.validate_and_filter(promos)
