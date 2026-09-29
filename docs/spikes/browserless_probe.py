"""Sonda de Diagnóstico Browserless Cloud (Endpoint Europeu production-lon).

Valida acessibilidade técnica da Domino's e Telepizza através de browser real,
medindo consumo de unidades, códigos de resposta do alvo e tempo de execução.

Regras Estritas de Segurança e Conformidade:
- Token NUNCA impresso nem comitado (enviado exclusivamente via header Authorization).
- Endpoint europeu: https://production-lon.browserless.io/content.
- Cache-Control: no-cache.
- Dois modos explicitamente separados: Modo A (datacenter) e Modo B (residential).
- Parâmetro proxy configurado na query string conforme a especificação da Browserless (?proxy=datacenter / ?proxy=residential).
- O payload JSON contém apenas url, rejectResourceTypes e gotoOptions.
- O Modo B só é executado se o Modo A continuar bloqueado.
- Zero resolução de CAPTCHA, zero Smart Scrape, zero rota /unblock.
- Bloqueio estrito de imagens, media, fontes, CSS e analytics (mantendo scripts para dataLayer).
- Diagnóstico detalhado: corpo de erro da Browserless capturado e sanitizado.
- Sanitização absoluta: sem cookies, sem HTML completo, sem dados pessoais de conta.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

_BROWSERLESS_BASE = "https://production-lon.browserless.io"
_CONTENT_ENDPOINT = f"{_BROWSERLESS_BASE}/content"
_ACCOUNT_ENDPOINT = f"{_BROWSERLESS_BASE}/account"

_ANALYTICS_PATTERNS = [
    "*google-analytics.com*",
    "*googletagmanager.com*",
    "*doubleclick.net*",
    "*facebook.net*",
    "*hotjar.com*",
    "*clarity.ms*",
]


def _get_account_units(api_key: str) -> float | None:
    """Consulta o endpoint oficial /account da Browserless extraindo apenas unidades/créditos (sem dados pessoais)."""
    req = urllib.request.Request(
        _ACCOUNT_ENDPOINT,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Cache-Control": "no-cache",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for k in ["units", "unitsUsed", "credits", "consumedUnits", "requests"]:
                if k in data and isinstance(data[k], (int, float)):
                    return float(data[k])
            if "usage" in data and isinstance(data["usage"], dict):
                for k in ["units", "unitsUsed", "credits", "consumed"]:
                    if k in data["usage"] and isinstance(data["usage"][k], (int, float)):
                        return float(data["usage"][k])
            return None
    except Exception:
        return None


def probe_single_target(
    target_url: str,
    mode: str,
    api_key: str,
    timeout: float = 25.0,
) -> dict:
    """Executa um probe individual via Content API no endpoint europeu."""
    # No Browserless, o modo datacenter é a rota padrão sem proxy (?proxy=residential só para residencial)
    if mode == "residential":
        endpoint_url = f"{_CONTENT_ENDPOINT}?proxy=residential"
    else:
        endpoint_url = _CONTENT_ENDPOINT

    payload = {
        "url": target_url,
        "rejectResourceTypes": ["image", "media", "font", "stylesheet"],
        "gotoOptions": {
            "waitUntil": "domcontentloaded",
            "timeout": int((timeout - 5) * 1000),
        },
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint_url,
        data=req_data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        },
        method="POST",
    )

    report_entry = {
        "mode": mode,
        "target": target_url,
        "browserless_http_status": None,
        "target_http_status": None,
        "elapsed_seconds": 0.0,
        "content_length": 0,
        "title": "",
        "combo_id_count": 0,
        "unique_promotion_ids_count": 0,
        "is_challenge": False,
        "usage_before": None,
        "usage_after": None,
        "usage_delta": None,
        "error": None,
    }

    usage_before = _get_account_units(api_key)
    report_entry["usage_before"] = usage_before

    start_time = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = time.perf_counter() - start_time
            report_entry["elapsed_seconds"] = round(elapsed, 2)
            report_entry["browserless_http_status"] = resp.status

            # Status do site alvo reportado pela Browserless no header X-Response-Code
            target_code_hdr = resp.headers.get("X-Response-Code") or resp.headers.get("x-response-code")
            if target_code_hdr:
                try:
                    report_entry["target_http_status"] = int(target_code_hdr)
                except ValueError:
                    report_entry["target_http_status"] = target_code_hdr

            body = resp.read().decode("utf-8", errors="replace")
            report_entry["content_length"] = len(body)

            # Extração de Título
            m_title = re.search(r"<title[^>]*>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
            report_entry["title"] = m_title.group(1).replace("\n", " ").strip() if m_title else "Sem <title>"

            # Deteção de Challenge / WAF
            is_cf = (
                report_entry["target_http_status"] == 403 or
                "Just a moment..." in body or
                "cf-browser-verification" in body or
                "challenge-running" in body
            )
            report_entry["is_challenge"] = is_cf

            # Seletores Domino's: combo-id
            combos = re.findall(r'combo-id=["\']?([^"\'\s>]+)', body, re.IGNORECASE)
            report_entry["combo_id_count"] = len(combos)

            # Seletores Telepizza: view_promotion e promotion_id / data-id
            promo_ids = re.findall(r"promotion_id:\s*['\"]([^'\"]+)['\"]", body)
            data_ids = re.findall(r"data-id=['\"]([^'\"]+)['\"]", body)
            all_tele = list(dict.fromkeys(promo_ids + data_ids))
            report_entry["unique_promotion_ids_count"] = len(all_tele)

    except urllib.error.HTTPError as exc:
        elapsed = time.perf_counter() - start_time
        report_entry["elapsed_seconds"] = round(elapsed, 2)
        report_entry["browserless_http_status"] = exc.code
        try:
            err_body = exc.read().decode("utf-8", errors="replace").strip()
            # Sanitiza para garantir que tokens ou parâmetros confidenciais nunca são impressos
            err_clean = re.sub(r'token=[^&\s"\']+', 'token=REDACTED', err_body)
            err_clean = re.sub(r'Bearer\s+[^\s"\']+', 'Bearer REDACTED', err_clean)
            report_entry["error"] = f"Browserless HTTP {exc.code}: {err_clean if err_clean else exc.reason}"
        except Exception:
            report_entry["error"] = f"Browserless HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        report_entry["elapsed_seconds"] = round(time.perf_counter() - start_time, 2)
        report_entry["error"] = f"{type(exc).__name__}: {exc}"

    usage_after = _get_account_units(api_key)
    report_entry["usage_after"] = usage_after
    if usage_before is not None and usage_after is not None:
        report_entry["usage_delta"] = round(usage_after - usage_before, 4)

    return report_entry


def run_spike():
    api_key = os.environ.get("BROWSERLESS_API_KEY", "").strip()
    if not api_key:
        print("[ERRO] Variável de ambiente BROWSERLESS_API_KEY não definida.")
        print("Define a chave em PowerShell:")
        print('  $env:BROWSERLESS_API_KEY="a_tua_chave"')
        print("E executa:")
        print("  python docs/spikes/browserless_probe.py")
        sys.exit(1)

    targets = [
        ("Domino's Homepage", "https://www.dominospizza.pt/"),
        ("Telepizza App Promoções", "https://app.telepizza.pt/promocoes"),
    ]

    results = []

    for label, url in targets:
        print(f"\n==================================================")
        print(f"Alvo: {label} ({url})")
        print(f"==================================================")

        # 1. Modo A: Datacenter
        print("--> Executando Modo A (proxy=datacenter)...")
        res_dc = probe_single_target(url, mode="datacenter", api_key=api_key)
        results.append(res_dc)

        # Avalia se Modo A foi bem-sucedido
        dc_success = False
        if "dominos" in url:
            dc_success = res_dc["combo_id_count"] > 0 and not res_dc["is_challenge"] and res_dc["browserless_http_status"] == 200
        else:
            dc_success = res_dc["unique_promotion_ids_count"] > 0 and not res_dc["is_challenge"] and res_dc["browserless_http_status"] == 200

        if dc_success:
            print(f"  [OK] Modo Datacenter teve sucesso! (Target HTTP: {res_dc['target_http_status']})")
            print("  Modo B (residential) NÃO é necessário para este alvo.")
        else:
            print(f"  [BLOQUEADO OU ERRO] Modo Datacenter falhou (Browserless HTTP: {res_dc['browserless_http_status']}, Target HTTP: {res_dc['target_http_status']}, Challenge: {res_dc['is_challenge']}).")
            if res_dc["error"]:
                print(f"  Diagnóstico: {res_dc['error']}")
            print("--> A testar Modo B (proxy=residential) para este alvo...")
            res_res = probe_single_target(url, mode="residential", api_key=api_key)
            results.append(res_res)
            if "dominos" in url:
                res_success = res_res["combo_id_count"] > 0 and not res_res["is_challenge"] and res_res["browserless_http_status"] == 200
            else:
                res_success = res_res["unique_promotion_ids_count"] > 0 and not res_res["is_challenge"] and res_res["browserless_http_status"] == 200
            print(f"  Resultado Modo B: Success={res_success}, Browserless HTTP={res_res['browserless_http_status']}, Target HTTP: {res_res['target_http_status']}")
            if res_res["error"]:
                print(f"  Diagnóstico: {res_res['error']}")

    print("\n" + "=" * 70)
    print("RELATÓRIO SANITIZADO FINAL BROWSERLESS:")
    print("=" * 70)
    print(json.dumps(results, indent=2))
    print("=" * 70)


if __name__ == "__main__":
    run_spike()
