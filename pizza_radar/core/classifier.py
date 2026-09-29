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
)

_PIZZA_KEYWORDS: tuple[str, ...] = (
    "pizza",
    "pizzas",
    "calzone",
    "massa fina",
    "massa pan",
    "rolling pizza",
    "clássica",
    "classica",
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
        has_non_pizza = bool(categories - {ComponentCategory.PIZZA})

        if has_pizza and has_non_pizza:
            return OfferType.BUNDLE_WITH_PIZZA
        if has_pizza and not has_non_pizza:
            return OfferType.PIZZA
        if not has_pizza and has_non_pizza:
            return OfferType.NON_PIZZA

    # 2. Avaliação de contagem explícita de pizzas
    has_explicit_pizzas = pizza_count is not None and pizza_count > 0

    text_to_check = f"{title} {description}".lower()

    has_pizza_term = any(
        re.search(r"\b" + re.escape(kw) + r"\b", text_to_check)
        for kw in _PIZZA_KEYWORDS
    ) or has_explicit_pizzas

    has_complement_term = any(
        re.search(r"\b" + re.escape(kw) + r"\b", text_to_check)
        for kw in _COMPLEMENT_KEYWORDS
    )

    # 3. Caso exclusivamente NÃO-PIZZA (bebidas, sobremesas, entradas isoladas)
    has_exclusive_non_pizza = any(
        re.search(r"\b" + re.escape(kw) + r"\b", text_to_check)
        for kw in _NON_PIZZA_EXCLUSIVE_KEYWORDS
    )

    if has_exclusive_non_pizza and not has_pizza_term:
        return OfferType.NON_PIZZA

    # 4. Caso BUNDLE (Pizza + Bebida / Sobremesa / Menu)
    if has_pizza_term and has_complement_term:
        return OfferType.BUNDLE_WITH_PIZZA

    # 5. Caso PIZZA pura
    if has_pizza_term:
        return OfferType.PIZZA

    # 6. Ofertas genéricas de desconto como '2x1', '50% na segunda' sem menção ao produto
    if "2x1" in text_to_check or "2 por 1" in text_to_check or "dobrar" in text_to_check:
        # Se for numa pizzaria e não menciona extras, mas não comprova que é pizza
        # É classificado como UNKNOWN para não entrar indevidamente em rankings restritos
        return OfferType.UNKNOWN

    return OfferType.UNKNOWN
