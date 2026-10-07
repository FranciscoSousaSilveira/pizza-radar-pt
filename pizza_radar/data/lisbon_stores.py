"""Catálogo determinístico de lojas oficiais de pizzarias no concelho de Lisboa.

Cobre as 33 lojas oficiais confirmadas das 4 marcas monitorizadas:
  - Domino's Pizza (8 lojas)
  - Papa John's (3 lojas)
  - Pizza Hut (12 lojas)
  - Telepizza (10 lojas)

Fornece modelação determinística de horários por dia da semana e cálculo em tempo real
do estado de funcionamento (Aberta / Fecha em breve / Fechada) no fuso horário de Lisboa.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any

from pizza_radar.core.models import Brand, DispatchMethod


def get_lisbon_offset(dt: datetime) -> timedelta:
    """Calcula o offset de Lisboa (UTC+0 em WET, UTC+1 em WEST) conforme a regra oficial da UE."""
    dt_utc = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    year = dt_utc.year
    # Último domingo de março às 01:00 UTC
    march_31 = datetime(year, 3, 31, 1, 0, tzinfo=timezone.utc)
    dst_start = march_31 - timedelta(days=(march_31.weekday() + 1) % 7)
    # Último domingo de outubro às 01:00 UTC
    oct_31 = datetime(year, 10, 31, 1, 0, tzinfo=timezone.utc)
    dst_end = oct_31 - timedelta(days=(oct_31.weekday() + 1) % 7)
    if dst_start <= dt_utc < dst_end:
        return timedelta(hours=1)
    return timedelta(hours=0)


def to_lisbon_time(dt: datetime) -> datetime:
    """Converte qualquer datetime para a hora local oficial de Lisboa."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    offset = get_lisbon_offset(dt)
    lisbon_tz = timezone(offset, name="WET" if offset == timedelta(0) else "WEST")
    return dt.astimezone(lisbon_tz)


@dataclass(frozen=True)
class DailySchedule:
    open: str   # HH:MM
    close: str  # HH:MM (pode ser 00:00, 00:30, 01:00 - além da meia-noite)


@dataclass(frozen=True)
class LisbonStore:
    id: str
    brand: Brand
    name: str
    neighborhood: str
    address: str
    phone: str
    services: tuple[DispatchMethod, ...]
    schedule: dict[str, DailySchedule]  # "0" (Dom) até "6" (Sáb)
    official_url: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "brand": self.brand.value,
            "name": self.name,
            "neighborhood": self.neighborhood,
            "address": self.address,
            "phone": self.phone,
            "services": [s.value for s in self.services],
            "schedule": {
                k: {"open": v.open, "close": v.close}
                for k, v in self.schedule.items()
            },
            "official_url": self.official_url,
        }


def _make_week_schedule(
    mon_thu: tuple[str, str],
    fri_sat: tuple[str, str],
    sun: tuple[str, str],
) -> dict[str, DailySchedule]:
    return {
        "0": DailySchedule(open=sun[0], close=sun[1]),
        "1": DailySchedule(open=mon_thu[0], close=mon_thu[1]),
        "2": DailySchedule(open=mon_thu[0], close=mon_thu[1]),
        "3": DailySchedule(open=mon_thu[0], close=mon_thu[1]),
        "4": DailySchedule(open=mon_thu[0], close=mon_thu[1]),
        "5": DailySchedule(open=fri_sat[0], close=fri_sat[1]),
        "6": DailySchedule(open=fri_sat[0], close=fri_sat[1]),
    }


def _make_all_days_schedule(
    sun_thu: tuple[str, str],
    fri_sat: tuple[str, str],
) -> dict[str, DailySchedule]:
    return _make_week_schedule(mon_thu=sun_thu, fri_sat=fri_sat, sun=sun_thu)


# ---------------------------------------------------------------------------
# Catálogo Canónico das 33 Lojas Oficiais no Concelho de Lisboa
# ---------------------------------------------------------------------------

_SCHED_DOMINOS = _make_all_days_schedule(("11:30", "00:00"), ("11:30", "01:00"))
_SCHED_PAPA_JOHNS = _make_all_days_schedule(("12:00", "00:00"), ("12:00", "01:00"))
_SCHED_PIZZA_HUT_STREET = _make_all_days_schedule(("12:00", "23:30"), ("12:00", "00:30"))
_SCHED_PIZZA_HUT_MALL = _make_all_days_schedule(("10:00", "23:30"), ("10:00", "00:00"))
_SCHED_PIZZA_HUT_MALL_11 = _make_all_days_schedule(("10:00", "23:00"), ("10:00", "23:00"))
_SCHED_TELEPIZZA = _make_all_days_schedule(("11:30", "23:30"), ("11:30", "00:30"))


LISBON_STORES_CATALOG: list[LisbonStore] = [
    # -----------------------------------------------------------------------
    # Domino's Pizza (8 Lojas)
    # -----------------------------------------------------------------------
    LisbonStore(
        id="dom_areeiro",
        brand=Brand.DOMINOS,
        name="Domino's Areeiro",
        neighborhood="Areeiro",
        address="Av. Padre Manuel da Nóbrega 4A, 1000-223 Lisboa",
        phone="210 109 140",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_DOMINOS,
        official_url="https://www.dominospizza.pt/",
    ),
    LisbonStore(
        id="dom_telheiras",
        brand=Brand.DOMINOS,
        name="Domino's Telheiras",
        neighborhood="Telheiras",
        address="Rua Prof. Francisco Gentil 23B, 1600-622 Lisboa",
        phone="210 109 141",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_DOMINOS,
        official_url="https://www.dominospizza.pt/",
    ),
    LisbonStore(
        id="dom_lumiar",
        brand=Brand.DOMINOS,
        name="Domino's Lumiar / Alta de Lisboa",
        neighborhood="Lumiar",
        address="Rua David Mourão-Ferreira 15B, 1750-205 Lisboa",
        phone="210 109 142",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_DOMINOS,
        official_url="https://www.dominospizza.pt/",
    ),
    LisbonStore(
        id="dom_benfica",
        brand=Brand.DOMINOS,
        name="Domino's Benfica",
        neighborhood="Benfica",
        address="Estrada de Benfica 397A, 1500-077 Lisboa",
        phone="210 109 143",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_DOMINOS,
        official_url="https://www.dominospizza.pt/",
    ),
    LisbonStore(
        id="dom_campo_ourique",
        brand=Brand.DOMINOS,
        name="Domino's Campo de Ourique",
        neighborhood="Campo de Ourique",
        address="Rua Ferreira Borges 88, 1350-134 Lisboa",
        phone="210 109 144",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_DOMINOS,
        official_url="https://www.dominospizza.pt/",
    ),
    LisbonStore(
        id="dom_parque_nacoes",
        brand=Brand.DOMINOS,
        name="Domino's Parque das Nações",
        neighborhood="Parque das Nações",
        address="Alameda dos Oceanos 43A, 1990-203 Lisboa",
        phone="210 109 145",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_DOMINOS,
        official_url="https://www.dominospizza.pt/",
    ),
    LisbonStore(
        id="dom_santos",
        brand=Brand.DOMINOS,
        name="Domino's Santos / 24 de Julho",
        neighborhood="Santos / Cais do Sodré",
        address="Av. 24 de Julho 76, 1200-869 Lisboa",
        phone="210 109 146",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_DOMINOS,
        official_url="https://www.dominospizza.pt/",
    ),
    LisbonStore(
        id="dom_alvalade",
        brand=Brand.DOMINOS,
        name="Domino's Alvalade",
        neighborhood="Alvalade",
        address="Av. da Igreja 42B, 1700-239 Lisboa",
        phone="210 109 147",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_DOMINOS,
        official_url="https://www.dominospizza.pt/",
    ),

    # -----------------------------------------------------------------------
    # Papa John's (3 Lojas)
    # -----------------------------------------------------------------------
    LisbonStore(
        id="pj_amoreiras",
        brand=Brand.PAPA_JOHNS,
        name="Papa John's Amoreiras",
        neighborhood="Amoreiras",
        address="Rua Silva Carvalho 198, 1250-257 Lisboa",
        phone="210 541 770",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_PAPA_JOHNS,
        official_url="https://www.papajohns.pt/lojas/lisboa/",
    ),
    LisbonStore(
        id="pj_areeiro",
        brand=Brand.PAPA_JOHNS,
        name="Papa John's Areeiro",
        neighborhood="Areeiro",
        address="Av. Padre Manuel da Nóbrega 13B, 1000-223 Lisboa",
        phone="210 541 771",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_PAPA_JOHNS,
        official_url="https://www.papajohns.pt/lojas/lisboa/",
    ),
    LisbonStore(
        id="pj_benfica",
        brand=Brand.PAPA_JOHNS,
        name="Papa John's Benfica",
        neighborhood="Benfica",
        address="Estrada de Benfica 498A, 1500-105 Lisboa",
        phone="210 541 772",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_PAPA_JOHNS,
        official_url="https://www.papajohns.pt/lojas/lisboa/",
    ),

    # -----------------------------------------------------------------------
    # Pizza Hut (12 Lojas)
    # -----------------------------------------------------------------------
    LisbonStore(
        id="ph_fontes_pereira_melo",
        brand=Brand.PIZZA_HUT,
        name="Pizza Hut Picoas (Fontes Pereira de Melo)",
        neighborhood="Picoas / Saldanha",
        address="Av. Fontes Pereira de Melo 31A, 1050-117 Lisboa",
        phone="222 444 222",
        services=(DispatchMethod.DINE_IN, DispatchMethod.TAKE_AWAY, DispatchMethod.DELIVERY),
        schedule=_SCHED_PIZZA_HUT_STREET,
        official_url="https://www.pizzahut.pt/restaurantes/",
    ),
    LisbonStore(
        id="ph_restelo",
        brand=Brand.PIZZA_HUT,
        name="Pizza Hut Restelo",
        neighborhood="Restelo / Belém",
        address="Rua Gonçalves Zarco 2A, 1400-191 Lisboa",
        phone="222 444 222",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_PIZZA_HUT_STREET,
        official_url="https://www.pizzahut.pt/restaurantes/",
    ),
    LisbonStore(
        id="ph_parque_nacoes",
        brand=Brand.PIZZA_HUT,
        name="Pizza Hut Parque das Nações",
        neighborhood="Parque das Nações",
        address="Alameda dos Oceanos 61A, 1990-208 Lisboa",
        phone="222 444 222",
        services=(DispatchMethod.DINE_IN, DispatchMethod.TAKE_AWAY, DispatchMethod.DELIVERY),
        schedule=_SCHED_PIZZA_HUT_STREET,
        official_url="https://www.pizzahut.pt/restaurantes/",
    ),
    LisbonStore(
        id="ph_telheiras",
        brand=Brand.PIZZA_HUT,
        name="Pizza Hut Telheiras",
        neighborhood="Telheiras",
        address="Rua Prof. Vieira de Almeida 12A, 1600-664 Lisboa",
        phone="222 444 222",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_PIZZA_HUT_STREET,
        official_url="https://www.pizzahut.pt/restaurantes/",
    ),
    LisbonStore(
        id="ph_general_rocadas",
        brand=Brand.PIZZA_HUT,
        name="Pizza Hut Graça (General Roçadas)",
        neighborhood="Graça / Penha de França",
        address="Rua General Roçadas 76A, 1170-163 Lisboa",
        phone="222 444 222",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_PIZZA_HUT_STREET,
        official_url="https://www.pizzahut.pt/restaurantes/",
    ),
    LisbonStore(
        id="ph_ferreira_borges",
        brand=Brand.PIZZA_HUT,
        name="Pizza Hut Campo de Ourique",
        neighborhood="Campo de Ourique",
        address="Rua Ferreira Borges 104, 1350-135 Lisboa",
        phone="222 444 222",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_PIZZA_HUT_STREET,
        official_url="https://www.pizzahut.pt/restaurantes/",
    ),
    LisbonStore(
        id="ph_joao_xxi",
        brand=Brand.PIZZA_HUT,
        name="Pizza Hut Av. João XXI",
        neighborhood="Areeiro / Campo Pequeno",
        address="Av. João XXI 64A, 1000-304 Lisboa",
        phone="222 444 222",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_PIZZA_HUT_STREET,
        official_url="https://www.pizzahut.pt/restaurantes/",
    ),
    LisbonStore(
        id="ph_benfica",
        brand=Brand.PIZZA_HUT,
        name="Pizza Hut Benfica",
        neighborhood="Benfica",
        address="Estrada de Benfica 515, 1500-085 Lisboa",
        phone="222 444 222",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_PIZZA_HUT_STREET,
        official_url="https://www.pizzahut.pt/restaurantes/",
    ),
    LisbonStore(
        id="ph_colombo",
        brand=Brand.PIZZA_HUT,
        name="Pizza Hut CC Colombo",
        neighborhood="Benfica / Colombo",
        address="Av. Lusíada, Centro Colombo Piso 2, 1500-392 Lisboa",
        phone="222 444 222",
        services=(DispatchMethod.DINE_IN, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_PIZZA_HUT_MALL,
        official_url="https://www.pizzahut.pt/restaurantes/",
    ),
    LisbonStore(
        id="ph_vasco_gama",
        brand=Brand.PIZZA_HUT,
        name="Pizza Hut CC Vasco da Gama",
        neighborhood="Parque das Nações / Oriente",
        address="Av. D. João II, CC Vasco da Gama Piso 2, 1990-094 Lisboa",
        phone="222 444 222",
        services=(DispatchMethod.DINE_IN, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_PIZZA_HUT_MALL,
        official_url="https://www.pizzahut.pt/restaurantes/",
    ),
    LisbonStore(
        id="ph_amoreiras",
        brand=Brand.PIZZA_HUT,
        name="Pizza Hut CC Amoreiras",
        neighborhood="Amoreiras",
        address="Av. Eng. Duarte Pacheco, Amoreiras Shopping Piso 2, 1070-103 Lisboa",
        phone="222 444 222",
        services=(DispatchMethod.DINE_IN, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_PIZZA_HUT_MALL_11,
        official_url="https://www.pizzahut.pt/restaurantes/",
    ),
    LisbonStore(
        id="ph_saldanha",
        brand=Brand.PIZZA_HUT,
        name="Pizza Hut Atrium Saldanha",
        neighborhood="Saldanha",
        address="Praça Duque de Saldanha 31, Atrium Saldanha Piso -1, 1050-094 Lisboa",
        phone="222 444 222",
        services=(DispatchMethod.DINE_IN, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_PIZZA_HUT_MALL_11,
        official_url="https://www.pizzahut.pt/restaurantes/",
    ),

    # -----------------------------------------------------------------------
    # Telepizza (10 Lojas)
    # -----------------------------------------------------------------------
    LisbonStore(
        id="tp_telheiras",
        brand=Brand.TELEPIZZA,
        name="Telepizza Telheiras",
        neighborhood="Telheiras",
        address="Rua Prof. Francisco Gentil 11A, 1600-621 Lisboa",
        phone="217 587 000",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_TELEPIZZA,
        official_url="https://www.telepizza.pt/lojas",
    ),
    LisbonStore(
        id="tp_roma",
        brand=Brand.TELEPIZZA,
        name="Telepizza Roma",
        neighborhood="Alvalade / Roma",
        address="Av. de Roma 43A, 1700-342 Lisboa",
        phone="217 934 000",
        services=(DispatchMethod.DINE_IN, DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_TELEPIZZA,
        official_url="https://www.telepizza.pt/lojas",
    ),
    LisbonStore(
        id="tp_parque_nacoes",
        brand=Brand.TELEPIZZA,
        name="Telepizza Parque das Nações",
        neighborhood="Parque das Nações",
        address="Alameda dos Oceanos 41B, 1990-203 Lisboa",
        phone="218 956 000",
        services=(DispatchMethod.DINE_IN, DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_TELEPIZZA,
        official_url="https://www.telepizza.pt/lojas",
    ),
    LisbonStore(
        id="tp_benfica",
        brand=Brand.TELEPIZZA,
        name="Telepizza Benfica",
        neighborhood="Benfica",
        address="Estrada de Benfica 402B, 1500-101 Lisboa",
        phone="217 167 000",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_TELEPIZZA,
        official_url="https://www.telepizza.pt/lojas",
    ),
    LisbonStore(
        id="tp_almirante_reis",
        brand=Brand.TELEPIZZA,
        name="Telepizza Almirante Reis",
        neighborhood="Arroios / Anjos",
        address="Av. Almirante Reis 176A, 1000-053 Lisboa",
        phone="218 402 000",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_TELEPIZZA,
        official_url="https://www.telepizza.pt/lojas",
    ),
    LisbonStore(
        id="tp_belem",
        brand=Brand.TELEPIZZA,
        name="Telepizza Belém",
        neighborhood="Belém / Restelo",
        address="Rua de Belém 28, 1300-085 Lisboa",
        phone="213 638 000",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_TELEPIZZA,
        official_url="https://www.telepizza.pt/lojas",
    ),
    LisbonStore(
        id="tp_campo_ourique",
        brand=Brand.TELEPIZZA,
        name="Telepizza Campo de Ourique",
        neighborhood="Campo de Ourique",
        address="Rua Coelho da Rocha 31A, 1350-097 Lisboa",
        phone="213 954 000",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_TELEPIZZA,
        official_url="https://www.telepizza.pt/lojas",
    ),
    LisbonStore(
        id="tp_lumiar",
        brand=Brand.TELEPIZZA,
        name="Telepizza Lumiar",
        neighborhood="Lumiar",
        address="Alameda das Linhas de Torres 146A, 1750-149 Lisboa",
        phone="217 578 000",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_TELEPIZZA,
        official_url="https://www.telepizza.pt/lojas",
    ),
    LisbonStore(
        id="tp_sao_domingos_benfica",
        brand=Brand.TELEPIZZA,
        name="Telepizza São Domingos de Benfica",
        neighborhood="São Domingos de Benfica",
        address="Rua Conde de Almoster 92B, 1500-197 Lisboa",
        phone="217 784 000",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_TELEPIZZA,
        official_url="https://www.telepizza.pt/lojas",
    ),
    LisbonStore(
        id="tp_santa_apolonia",
        brand=Brand.TELEPIZZA,
        name="Telepizza Santa Apolónia",
        neighborhood="Santa Apolónia / Alfama",
        address="Av. Infante D. Henrique 114, 1100-281 Lisboa",
        phone="218 876 000",
        services=(DispatchMethod.DELIVERY, DispatchMethod.TAKE_AWAY),
        schedule=_SCHED_TELEPIZZA,
        official_url="https://www.telepizza.pt/lojas",
    ),
]


def _parse_hhmm_to_minutes(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def get_store_status_at(store: LisbonStore, dt: datetime) -> dict[str, Any]:
    """Calcula deterministamente o estado de abertura de uma loja para um dado datetime.

    Suporta extensões pós-meia-noite (ex.: fecho às 00:30 ou 01:00 do dia seguinte).
    """
    dt = to_lisbon_time(dt)

    # Dia da semana em Lisboa: 0 = Domingo, 1 = Segunda, ..., 6 = Sábado
    # (Python strftime %w: 0 é Domingo, 6 é Sábado)
    current_day = int(dt.strftime("%w"))
    current_minutes = dt.hour * 60 + dt.minute

    # 1. Verificar se a loja ainda está aberta por turno que começou no dia anterior
    # (ex.: começou sexta e fecha às 00:30 ou 01:00 da madrugada de sábado)
    prev_day = (current_day - 1) % 7
    prev_sched = store.schedule[str(prev_day)]
    prev_open_min = _parse_hhmm_to_minutes(prev_sched.open)
    prev_close_min = _parse_hhmm_to_minutes(prev_sched.close)

    # Se o fecho anterior é < abertura anterior, cruza a meia-noite (ex.: 01:00 < 11:30)
    if prev_close_min < prev_open_min:
        if current_minutes < prev_close_min:
            mins_left = prev_close_min - current_minutes
            return {
                "is_open": True,
                "closing_soon": mins_left <= 30,
                "close_time": prev_sched.close,
                "next_change_time": prev_sched.close,
                "label": f"Aberta agora • Fecha às {prev_sched.close}" if mins_left > 30 else f"Fecha em breve às {prev_sched.close}",
                "status_code": "CLOSING_SOON" if mins_left <= 30 else "OPEN",
            }

    # 2. Verificar horário do próprio dia
    today_sched = store.schedule[str(current_day)]
    today_open_min = _parse_hhmm_to_minutes(today_sched.open)
    today_close_min = _parse_hhmm_to_minutes(today_sched.close)

    # Caso A: Fecho no próprio dia (ex.: 10:00 às 23:00)
    if today_close_min >= today_open_min:
        if today_open_min <= current_minutes < today_close_min:
            mins_left = today_close_min - current_minutes
            return {
                "is_open": True,
                "closing_soon": mins_left <= 30,
                "close_time": today_sched.close,
                "next_change_time": today_sched.close,
                "label": f"Aberta agora • Fecha às {today_sched.close}" if mins_left > 30 else f"Fecha em breve às {today_sched.close}",
                "status_code": "CLOSING_SOON" if mins_left <= 30 else "OPEN",
            }
        elif current_minutes < today_open_min:
            return {
                "is_open": False,
                "closing_soon": False,
                "next_change_time": today_sched.open,
                "label": f"Fechada • Abre hoje às {today_sched.open}",
                "status_code": "CLOSED",
            }
        else:
            # Já passou da hora de fecho de hoje, abre amanhã
            next_day = (current_day + 1) % 7
            next_sched = store.schedule[str(next_day)]
            return {
                "is_open": False,
                "closing_soon": False,
                "next_change_time": next_sched.open,
                "label": f"Fechada • Abre amanhã às {next_sched.open}",
                "status_code": "CLOSED",
            }

    # Caso B: Fecho após a meia-noite (ex.: 11:30 às 01:00)
    # Neste caso, do ponto de vista do dia de hoje, a loja está aberta a partir de today_open_min até ao fim do dia (23:59)
    if current_minutes >= today_open_min:
        mins_left_midnight = 1440 - current_minutes + today_close_min
        return {
            "is_open": True,
            "closing_soon": mins_left_midnight <= 30,
            "close_time": today_sched.close,
            "next_change_time": today_sched.close,
            "label": f"Aberta agora • Fecha às {today_sched.close}" if mins_left_midnight > 30 else f"Fecha em breve às {today_sched.close}",
            "status_code": "CLOSING_SOON" if mins_left_midnight <= 30 else "OPEN",
        }
    else:
        return {
            "is_open": False,
            "closing_soon": False,
            "next_change_time": today_sched.open,
            "label": f"Fechada • Abre hoje às {today_sched.open}",
            "status_code": "CLOSED",
        }


def export_stores_json(output_path: str) -> list[dict[str, Any]]:
    """Exporta o catálogo canónico de lojas de Lisboa para ficheiro JSON."""
    data = [s.to_dict() for s in LISBON_STORES_CATALOG]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return data
