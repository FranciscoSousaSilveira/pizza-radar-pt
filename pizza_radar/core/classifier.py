"""Classificador determinístico da natureza do produto em ofertas promocionais.

Regras e Princípios de Engenharia:
1. Classificação 100% determinística baseada exclusivamente em evidências explícitas:
   - Componentes estruturados (included_items);
   - Contagem explícita de pizzas (pizza_count);
   - Termos inequívocos no título e descrição da oferta.
2. Proibição absoluta de modelos de IA/LLMs em tempo de execução.
3. Prevenção de falsos positivos: produtos como refrigerantes, copos gelados ou pão de alho
   são isolados como NON_PIZZA para nunca determinarem a 'pizza mais barata'.
"""

from __future__ import annotations

import re
from typing import Sequence

from pizza_radar.core.models import ComponentCategory, OfferComponent, OfferType


_NON_PIZZA_EXCLUSIVE_KEYWORDS: tuple[str, ...] = (
    "refrigerante",
    "refrigerantes",
    "coca-cola",
    "coca cola",
    "pepsi",
    "sumo",
    "sumos",
    "agua",
    "água",
    "cerveja",
    "cervejas",
    "ice tea",
    "nestea",
    "bebida",
    "bebidas",
    "gelado",
    "gelados",
    "ben & jerry",
    "ben&jerry",
    "copo gelado",
    "sobremesa",
    "sobremesas",
    "cookie",
    "cookies",
    "brownie",
    "brownies",
    "pao de alho",
    "pão de alho",
    "rolinhos",
    "asas de frango",
    "chicken wings",
    "frango",
    "frangos",
    "strips",
    "nuggets",
    "batatas",
    "garlic bread",
)

_COMPLEMENT_KEYWORDS: tuple[str, ...] = (
    "refrigerante",
    "refrigerantes",
    "bebida",
    "bebidas",
    "gelado",
    "gelados",
    "sobremesa",
    "sobremesas",
    "pao de alho",
    "pão de alho",
    "rolinhos",
    "asas",
    "menu",
    "combo",
    "pack",
    "entrada",
    "entradas",
)

_PIZZA_KEYWORDS: tuple[str, ...] = (
    "pizza",
    "pizzas",
    "calzone",
    "massa fina",
    "massa pan",
    "rolling pizza",
)

# Padrões específicos de bundles / menus combinados conhecidos
_KNOWN_BUNDLE_PATTERNS: tuple[str, ...] = (
    r"\bsuper\s+john\b",
    r"\bo\s+papito\b",
    r"\bcombo\s+(m[eé]dio|grande)\b",
    r"\bparty\s+combo\b",
    r"\btrio\s+bestial\s*\+",
    r"\bduo\s+bestial\s*\+",
    r"\bm[eé]dia\s*[\+\&]\s*entrada\s*[\+\&]\s*bebidas?\b",
    r"\bgrande\s*[\+\&]\s*entrada\s*[\+\&]\s*bebidas?\b",
)

# Padrões específicos de campanhas de pizza conhecidas
_KNOWN_PIZZA_PATTERNS: tuple[str, ...] = (
    r"\bpapa\s+[aà]s\s+3[aª]('?s)?\b",
    r"\btrio\s+bestial\b",
    r"\bduo\s+bestial\b",
    r"\b\d+\s+m[eé]dias\b",
    r"\b\d+\s+grandes\b",
)


def classify_offer_type(
    title: str,
    description: str = "",
    included_items: Sequence[OfferComponent] | None = None,
    pizza_count: int | None = None,
) -> OfferType:
    """Classifica deterministicamente a oferta entre PIZZA, BUNDLE_WITH_PIZZA, NON_PIZZA ou UNKNOWN.

    Args:
        title: Título da promoção anunciado pela marca.
        description: Descrição da promoção ou ingredientes.
        included_items: Componentes explícitos da oferta, se disponíveis.
        pizza_count: Número comprovado de pizzas, se fornecido.

    Returns:
        OfferType determinístico.
    """
    # 1. Avaliação prioritária via included_items estruturados
    if included_items:
        categories = {item.category for item in included_items}
        has_pizza = ComponentCategory.PIZZA in categories
        has_proven_non_pizza = bool(
            categories & {
                ComponentCategory.DRINK,
                ComponentCategory.SIDE,
                ComponentCategory.DESSERT,
            }
        )
        has_other = ComponentCategory.OTHER in categories

        if has_pizza and (has_proven_non_pizza or has_other):
            return OfferType.BUNDLE_WITH_PIZZA
        if has_pizza and not (has_proven_non_pizza or has_other):
            return OfferType.PIZZA
        if not has_pizza and has_proven_non_pizza:
            return OfferType.NON_PIZZA
        if not has_pizza and has_other and not has_proven_non_pizza:
            return OfferType.UNKNOWN

    # 2. Avaliação de contagem explícita de pizzas
    has_explicit_pizzas = pizza_count is not None and pizza_count > 0

    title_clean = title.strip().rstrip(".")
    text_to_check = f"{title_clean} {description}".lower()

    # 3. Padrões explícitos conhecidos de BUNDLE (Menus combinados)
    if any(re.search(pat, text_to_check) for pat in _KNOWN_BUNDLE_PATTERNS):
        return OfferType.BUNDLE_WITH_PIZZA

    # 4. Padrões explícitos conhecidos de PIZZA
    has_known_pizza_pattern = any(
        re.search(pat, text_to_check) for pat in _KNOWN_PIZZA_PATTERNS
    )

    has_pizza_term = (
        any(re.search(r"\b" + re.escape(kw) + r"\b", text_to_check) for kw in _PIZZA_KEYWORDS)
        or has_explicit_pizzas
        or has_known_pizza_pattern
    )

    has_complement_term = any(
        re.search(r"\b" + re.escape(kw) + r"\b", text_to_check)
        for kw in _COMPLEMENT_KEYWORDS
    )

    # 5. Caso exclusivamente NÃO-PIZZA (bebidas, sobremesas, entradas isoladas)
    has_exclusive_non_pizza = any(
        re.search(r"\b" + re.escape(kw) + r"\b", text_to_check)
        for kw in _NON_PIZZA_EXCLUSIVE_KEYWORDS
    )

    if has_exclusive_non_pizza and not has_pizza_term:
        return OfferType.NON_PIZZA

    # 6. Caso BUNDLE (Pizza + Bebida / Sobremesa / Menu)
    if has_pizza_term and has_complement_term:
        return OfferType.BUNDLE_WITH_PIZZA

    # 7. Caso PIZZA pura
    if has_pizza_term:
        return OfferType.PIZZA

    # 8. Ofertas genéricas de desconto como '2x1', '50% na segunda' sem menção ao produto
    if "2x1" in text_to_check or "2 por 1" in text_to_check or "dobrar" in text_to_check:
        return OfferType.UNKNOWN

    return OfferType.UNKNOWN
