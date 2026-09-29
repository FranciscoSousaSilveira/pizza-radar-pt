"""Testes unitários determinísticos para classificação de tipo de oferta (Issue #25).

Invariantes de Engenharia:
1. Zero IA em runtime (100% determinístico e previsível).
2. Itens não-pizza (refrigerantes, gelados, sobremesas, pão de alho) classificados como NON_PIZZA.
3. Pizzas com complementos classificadas como BUNDLE_WITH_PIZZA.
4. Pizzas isoladas ou combinadas classificadas como PIZZA.
5. Inconclusivo ou não comprovado classificado como UNKNOWN.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import unittest

from pizza_radar.adapters.papa_johns import PapaJohnsAdapter
from pizza_radar.core.classifier import classify_offer_type
from pizza_radar.core.models import (
    ComponentCategory,
    OfferComponent,
    OfferType,
    PizzaSize,
    UnifiedPromo,
    Brand,
)
from pizza_radar.engine.identity import group_promos_for_visual_presentation
from pizza_radar.engine.rankings import rank_by_lowest_price, rank_by_unit_price
from pizza_radar.persistence.exporter import generate_snapshot_dict
from pizza_radar.persistence.repository import SQLitePromotionRepository


class TestOfferClassifier(unittest.TestCase):
    """Testa a função classify_offer_type e o isolamento de produtos."""

    def test_non_pizza_drinks_and_desserts(self) -> None:
        """Confirma que refrigerantes, gelados e sobremesas são categoricamente classificados como NON_PIZZA."""
        cases = [
            ("2 Refrigerantes 1.5L", "Coca-cola, Fanta ou Sprite à escolha"),
            ("Copo Gelado Ben & Jerry's", "Chocolate Fudge Brownie 465ml"),
            ("Pão de Alho Supremo", "Pão de alho crocante com queijo mozarela"),
            ("Asas de Frango Barbecue", "6 unidades com molho barbecue"),
            ("Batatas Rústicas", "Porção individual com molho de alho"),
            ("Cookie Chocolate", "Cookie artesanal com pepitas"),
        ]
        for title, desc in cases:
            with self.subTest(title=title):
                res = classify_offer_type(title=title, description=desc)
                self.assertEqual(
                    res,
                    OfferType.NON_PIZZA,
                    f"'{title}' deveria ser NON_PIZZA mas foi {res}",
                )

    def test_bundle_with_pizza(self) -> None:
        """Confirma que menus com pizza + bebida/acompanhamento são classificados como BUNDLE_WITH_PIZZA."""
        cases = [
            ("Menu Individual Pizza + Bebida", "1 Pizza Média e 1 Refrigerante de lata"),
            ("Pack Família 2 Pizzas + Gelado", "2 Pizzas Grandes e 1 copo Ben & Jerry's"),
            ("Combo Pizza + Pão de Alho", "Pizza média clássica com pão de alho"),
        ]
        for title, desc in cases:
            with self.subTest(title=title):
                res = classify_offer_type(title=title, description=desc)
                self.assertEqual(
                    res,
                    OfferType.BUNDLE_WITH_PIZZA,
                    f"'{title}' deveria ser BUNDLE_WITH_PIZZA mas foi {res}",
                )

    def test_pure_pizza(self) -> None:
        """Confirma que ofertas de pizza pura são classificadas como PIZZA."""
        cases = [
            ("Pizza Média 3 Ingredientes", "Massa fina com mozarela e 3 ingredientes"),
            ("2 Pizzas Grandes Pan", "2 pizzas grandes massa pan clássica"),
            ("Calzone Especial", "Calzone recheado com queijo e fiambre"),
        ]
        for title, desc in cases:
            with self.subTest(title=title):
                res = classify_offer_type(title=title, description=desc)
                self.assertEqual(
                    res,
                    OfferType.PIZZA,
                    f"'{title}' deveria ser PIZZA mas foi {res}",
                )

    def test_explicit_pizza_count_overrides_unknown(self) -> None:
        """Se pizza_count for informado explicitamente (> 0), a oferta é reconhecida como pizza."""
        res = classify_offer_type(title="Oferta Especial", description="Preço de amigo", pizza_count=2)
        self.assertEqual(res, OfferType.PIZZA)

    def test_unknown_when_unproven(self) -> None:
        """Termos genéricos sem prova de produto mantêm-se como UNKNOWN."""
        cases = [
            ("Segundas a Dobrar", "Pede 1 e leva 2"),
            ("Super Desconto 50%", "Desconto imediato em toda a carta"),
        ]
        for title, desc in cases:
            with self.subTest(title=title):
                res = classify_offer_type(title=title, description=desc)
                self.assertEqual(res, OfferType.UNKNOWN)

    def test_structured_included_items_precedence(self) -> None:
        """A presença de included_items estruturados tem precedência sobre texto."""
        # Apenas pizza
        res_pizza = classify_offer_type(
            title="Promoção",
            included_items=[OfferComponent(category=ComponentCategory.PIZZA, quantity=1)],
        )
        self.assertEqual(res_pizza, OfferType.PIZZA)

        # Pizza + Drink
        res_bundle = classify_offer_type(
            title="Promoção",
            included_items=[
                OfferComponent(category=ComponentCategory.PIZZA, quantity=1),
                OfferComponent(category=ComponentCategory.DRINK, quantity=2),
            ],
        )
        self.assertEqual(res_bundle, OfferType.BUNDLE_WITH_PIZZA)

        # Apenas Drink
        res_drink = classify_offer_type(
            title="Promoção",
            included_items=[OfferComponent(category=ComponentCategory.DRINK, quantity=2)],
        )
        self.assertEqual(res_drink, OfferType.NON_PIZZA)


class TestPizzaOnlyMetricsIsolation(unittest.TestCase):
    """Testa o isolamento de métricas para impedir que complementos determinem rankings de pizza."""

    def test_non_pizza_excluded_from_best_unit_price(self) -> None:
        """Itens NON_PIZZA e UNKNOWN nunca entram no ranking BEST_UNIT_PRICE."""
        # Refrigerante a 2.99€ (299 cents)
        p_drink = UnifiedPromo(
            id="pj_drink",
            vendor=Brand.PAPA_JOHNS,
            title="2 Refrigerantes 1.5L",
            description="Coca-cola",
            observed_at="2026-09-29T12:00:00+00:00",
            price_cents=299,
            offer_type=OfferType.NON_PIZZA,
        )

        # Pizza a 11.99€ (1199 cents, 1 pizza)
        p_pizza = UnifiedPromo(
            id="pj_pizza",
            vendor=Brand.PAPA_JOHNS,
            title="Pizza Média Clássica",
            description="1 Pizza média",
            observed_at="2026-09-29T12:00:00+00:00",
            price_cents=1199,
            pizza_count=1,
            pizza_size=PizzaSize.MEDIUM,
            offer_type=OfferType.PIZZA,
        )

        groups = group_promos_for_visual_presentation([p_drink, p_pizza])
        self.assertEqual(len(groups), 2)

        # Ranking de preço unitário por pizza
        ranked = rank_by_unit_price(groups)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].item.vendor, Brand.PAPA_JOHNS)
        self.assertIn("Pizza Média", ranked[0].item.title)
        self.assertEqual(ranked[0].score, 1199)

    def test_lowest_price_ranking_with_pizza_only_toggle(self) -> None:
        """LOWEST_ABSOLUTE_PRICE com pizza_only=True filtra ofertas não-pizza."""
        p_drink = UnifiedPromo(
            id="pj_drink",
            vendor=Brand.PAPA_JOHNS,
            title="Copo Gelado Ben & Jerry's",
            description="Gelado 465ml",
            observed_at="2026-09-29T12:00:00+00:00",
            price_cents=649,
            offer_type=OfferType.NON_PIZZA,
        )
        p_pizza = UnifiedPromo(
            id="pj_pizza",
            vendor=Brand.PAPA_JOHNS,
            title="Pizza Média",
            description="Massa tradicional",
            observed_at="2026-09-29T12:00:00+00:00",
            price_cents=999,
            pizza_count=1,
            offer_type=OfferType.PIZZA,
        )

        groups = group_promos_for_visual_presentation([p_drink, p_pizza])

        # Sem filtro de pizza: gelado a 6.49€ fica em #1
        ranked_all = rank_by_lowest_price(groups, pizza_only=False)
        self.assertEqual(len(ranked_all), 2)
        self.assertEqual(ranked_all[0].score, 649)

        # Com pizza_only=True: apenas a pizza a 9.99€ é elegível
        ranked_pizza = rank_by_lowest_price(groups, pizza_only=True)
        self.assertEqual(len(ranked_pizza), 1)
        self.assertEqual(ranked_pizza[0].score, 999)
        self.assertIn("Pizza", ranked_pizza[0].item.title)


class TestPapaJohnsCampaignRegression(unittest.TestCase):
    """Testa regressão estrita de classificação para as campanhas reais da Papa John's."""

    def test_campaign_papa_as_3as(self) -> None:
        """“Papa às 3ª’s” -> PIZZA."""
        self.assertEqual(classify_offer_type("Papa às 3ª’s"), OfferType.PIZZA)
        self.assertEqual(classify_offer_type("Papa às 3as"), OfferType.PIZZA)

    def test_campaign_super_john(self) -> None:
        """“Super John” / “Super John.” -> BUNDLE_WITH_PIZZA."""
        self.assertEqual(classify_offer_type("Super John"), OfferType.BUNDLE_WITH_PIZZA)
        self.assertEqual(classify_offer_type("Super John."), OfferType.BUNDLE_WITH_PIZZA)

    def test_campaign_drinks_and_desserts(self) -> None:
        """“2 refrigerantes” e “Copo Gelado” -> NON_PIZZA."""
        self.assertEqual(classify_offer_type("2 refrigerantes"), OfferType.NON_PIZZA)
        self.assertEqual(classify_offer_type("Copo Gelado"), OfferType.NON_PIZZA)

    def test_campaign_trio_bestial(self) -> None:
        """“Trio Bestial” / “Trio Bestial.” -> PIZZA; “Trio Bestial +” -> BUNDLE_WITH_PIZZA."""
        self.assertEqual(classify_offer_type("Trio Bestial", "3 Médias"), OfferType.PIZZA)
        self.assertEqual(classify_offer_type("Trio Bestial."), OfferType.PIZZA)
        self.assertEqual(classify_offer_type("Trio Bestial +", "3 Médias + Entrada"), OfferType.BUNDLE_WITH_PIZZA)

    def test_campaign_combo_medio(self) -> None:
        """“Combo Médio” -> BUNDLE_WITH_PIZZA."""
        self.assertEqual(classify_offer_type("Combo Médio", "Média + Entrada + Bebidas"), OfferType.BUNDLE_WITH_PIZZA)

    def test_campaign_o_papito(self) -> None:
        """“O Papito” -> BUNDLE_WITH_PIZZA."""
        self.assertEqual(classify_offer_type("O Papito"), OfferType.BUNDLE_WITH_PIZZA)

    def test_campaign_duo_bestial(self) -> None:
        """“Duo Bestial” -> PIZZA."""
        self.assertEqual(classify_offer_type("Duo Bestial", "2 Médias"), OfferType.PIZZA)

    def test_campaign_combo_grande(self) -> None:
        """“Combo Grande” -> BUNDLE_WITH_PIZZA."""
        self.assertEqual(classify_offer_type("Combo Grande", "Grande + Entrada + Bebida"), OfferType.BUNDLE_WITH_PIZZA)

    def test_campaign_party_combo(self) -> None:
        """“Party Combo” -> BUNDLE_WITH_PIZZA."""
        self.assertEqual(classify_offer_type("Party Combo", "4 Médias"), OfferType.BUNDLE_WITH_PIZZA)

    def test_classica_alone_does_not_prove_pizza(self) -> None:
        """Palavras vagas como 'clássica' não provam pizza (Strict Rule)."""
        self.assertEqual(
            classify_offer_type("Sobremesa Clássica", "Receita tradicional de bolacha"),
            OfferType.NON_PIZZA,
        )
        self.assertEqual(
            classify_offer_type("Receita Clássica", "Massa crocante com molho especial"),
            OfferType.UNKNOWN,
        )

    def test_component_category_other_alone_gives_unknown(self) -> None:
        """ComponentCategory.OTHER isolado tem de dar UNKNOWN, nunca NON_PIZZA."""
        res = classify_offer_type(
            title="Promoção Genérica",
            included_items=[OfferComponent(category=ComponentCategory.OTHER, description="Artigo")],
        )
        self.assertEqual(res, OfferType.UNKNOWN)

    def test_drink_side_dessert_without_pizza_gives_non_pizza(self) -> None:
        """DRINK, SIDE ou DESSERT sem pizza comprovada dá NON_PIZZA."""
        for cat in (ComponentCategory.DRINK, ComponentCategory.SIDE, ComponentCategory.DESSERT):
            with self.subTest(category=cat):
                res = classify_offer_type(
                    title="Item",
                    included_items=[OfferComponent(category=cat, description="Complemento")],
                )
                self.assertEqual(res, OfferType.NON_PIZZA)


class TestPapaJohnsRealCampaignsFixture(unittest.TestCase):
    """Testa a fixture papa_johns_campaigns.json e os rankings resultantes."""

    @classmethod
    def setUpClass(cls) -> None:
        fixture_path = Path(__file__).resolve().parent / "fixtures" / "papa_johns_campaigns.json"
        with open(fixture_path, encoding="utf-8") as f:
            cls.raw_data = json.load(f)

        adapter = PapaJohnsAdapter()
        parsed = adapter.parse(cls.raw_data, store_id="2", dispatch_method="in_store")
        observed = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
        cls.promos = [adapter.adapt(item, observed_at=observed) for item in parsed]
        cls.promos_by_name = {p.title: p for p in cls.promos}

    def test_all_eleven_campaigns_present_and_classified(self) -> None:
        """Verifica a classificação e contagem de cada uma das 11 campanhas da fixture."""
        expected = {
            "Papa às 3ª’s": (OfferType.PIZZA, None, PizzaSize.UNKNOWN, False),
            "Super John.": (OfferType.BUNDLE_WITH_PIZZA, None, PizzaSize.UNKNOWN, False),
            "2 refrigerantes": (OfferType.NON_PIZZA, None, PizzaSize.UNKNOWN, False),
            "Copo Gelado": (OfferType.NON_PIZZA, None, PizzaSize.UNKNOWN, False),
            "Trio Bestial.": (OfferType.PIZZA, 3, PizzaSize.MEDIUM, True),
            "Trio Bestial +": (OfferType.BUNDLE_WITH_PIZZA, 3, PizzaSize.MEDIUM, True),
            "Combo Médio": (OfferType.BUNDLE_WITH_PIZZA, 1, PizzaSize.MEDIUM, True),
            "O Papito": (OfferType.BUNDLE_WITH_PIZZA, None, PizzaSize.UNKNOWN, False),
            "Duo Bestial": (OfferType.PIZZA, 2, PizzaSize.MEDIUM, True),
            "Combo Grande": (OfferType.BUNDLE_WITH_PIZZA, 1, PizzaSize.LARGE, True),
            "Party Combo": (OfferType.BUNDLE_WITH_PIZZA, 4, PizzaSize.MEDIUM, True),
        }

        for name, (exp_type, exp_count, exp_size, exp_comp) in expected.items():
            with self.subTest(campaign=name):
                self.assertIn(name, self.promos_by_name)
                p = self.promos_by_name[name]
                self.assertEqual(p.offer_type, exp_type, f"Tipo de {name} incorreto")
                self.assertEqual(p.pizza_count, exp_count, f"pizza_count de {name} incorreto")
                self.assertEqual(p.pizza_size, exp_size, f"pizza_size de {name} incorreto")
                self.assertEqual(p.is_comparable_for_unit_price, exp_comp, f"Comparabilidade de {name} incorreta")

    def test_unit_price_ranking_with_fixture(self) -> None:
        """Confirma que BEST_UNIT_PRICE é liderado pelo Trio Bestial (7.99€/pizza) e exclui complementos."""
        groups = group_promos_for_visual_presentation(self.promos)
        ranked = rank_by_unit_price(groups)

        # Apenas as 6 ofertas com pizza_count comprovado e tipo pizza/bundle são elegíveis
        self.assertEqual(len(ranked), 6)
        titles_ranked = [r.item.title for r in ranked]

        # Trio Bestial (23.97 / 3 = 7.99€) deve ser #1
        self.assertEqual(ranked[0].score, 799)
        self.assertIn("Trio Bestial", ranked[0].item.title)

        # Não-pizzas e não comprovadas nunca podem surgir
        for forbidden in ("2 refrigerantes", "Copo Gelado", "Papa às 3ª’s", "Super John.", "O Papito"):
            self.assertNotIn(forbidden, titles_ranked)

    def test_lowest_price_ranking_with_fixture(self) -> None:
        """Com pizza_only=True, complementos não-pizza são excluídos do menor preço absoluto."""
        groups = group_promos_for_visual_presentation(self.promos)
        ranked_pizza_only = rank_by_lowest_price(groups, pizza_only=True)
        ranked_titles = [r.item.title for r in ranked_pizza_only]

        self.assertNotIn("2 refrigerantes", ranked_titles)
        self.assertNotIn("Copo Gelado", ranked_titles)
        # O Papito (7.99€) é a opção de pizza mais barata em valor absoluto
        self.assertEqual(ranked_pizza_only[0].score, 799)
        self.assertIn("O Papito", ranked_pizza_only[0].item.title)


class TestSnapshotSanitization(unittest.TestCase):
    """Testa que o snapshot público gerado não inclui error_message e usa status padronizados."""

    def test_vendor_status_sanitized(self) -> None:
        repo = SQLitePromotionRepository(":memory:")
        repo.init_schema()

        # Registar uma sincronização com erro técnico
        repo.record_vendor_sync_run(
            vendor=Brand.DOMINOS,
            status="FAILED",
            offers_found=0,
            error_message="NetworkError: HTTP 403 Forbidden at https://www.dominospizza.pt/ajax/order.php: Forbidden",
        )

        snapshot = generate_snapshot_dict(repo)
        vendor_status = snapshot.get("vendor_status", {})
        dominos_info = vendor_status.get("DOMINOS")

        self.assertIsNotNone(dominos_info)
        # 1. error_message NÃO pode estar presente no snapshot público
        self.assertNotIn("error_message", dominos_info)
        # 2. Status deve ser FAILED (já que não há ofertas ativas)
        self.assertEqual(dominos_info["status"], "FAILED")
        # 3. Status válidos do contrato
        valid_statuses = {"SUCCESS", "STALE", "FAILED", "PENDING"}
        for brand_key, info in vendor_status.items():
            self.assertIn(info["status"], valid_statuses, f"Status inválido para {brand_key}")
            self.assertNotIn("error_message", info, f"error_message exposta em {brand_key}")


if __name__ == "__main__":
    unittest.main()
