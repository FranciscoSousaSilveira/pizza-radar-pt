"""Última Sonda de Diagnóstico Browserless — Telepizza com Proxy Residencial.

Executa uma única chamada estritamente contra https://app.telepizza.pt/promocoes
via Browserless Content API no endpoint europeu com proxy=residential.
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
_CONTENT_ENDPOINT = f"{_BROWSERLESS_BASE}/content?proxy=residential"
_ACCOUNT_ENDPOINT = f"{_BROWSERLESS_BASE}/account"


def _get_account_units(api_key: str) -> float | None:
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


def run_probe():
    api_key = os.environ.get("BROWSERLESS_API_KEY", "").strip()
    if not api_key:
        print("[ERRO] Variável de ambiente BROWSERLESS_API_KEY não definida.")
        print('Define em PowerShell: $env:BROWSERLESS_API_KEY="a_tua_chave"')
        sys.exit(1)

    target_url = "https://app.telepizza.pt/promocoes"
    timeout = 28.0

    payload = {
        "url": target_url,
        "rejectResourceTypes": ["image", "media", "font", "stylesheet"],
        "rejectRequestPattern": ["*analytics*", "*gtm*", "*googletag*", "*hotjar*", "*facebook*"],
        "gotoOptions": {
            "waitUntil": "domcontentloaded",
            "timeout": 22000,
        },
    }

    report = {
        "target": target_url,
        "proxy": "residential",
        "browserless_http_status": None,
        "target_http_status": None,
        "elapsed_seconds": 0.0,
        "title": "",
        "content_length": 0,
        "has_view_promotion": False,
        "unique_promotion_ids_count": 0,
        "first_five_ids": [],
        "is_challenge": False,
        "consumed_units": None,
        "billed_bandwidth": None,
        "usage_before": None,
        "usage_after": None,
        "usage_delta": None,
        "error": None,
    }

    report["usage_before"] = _get_account_units(api_key)

    req = urllib.request.Request(
        _CONTENT_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        },
        method="POST",
    )

    start_time = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            report["elapsed_seconds"] = round(time.perf_counter() - start_time, 2)
            report["browserless_http_status"] = resp.status

            target_code = resp.headers.get("X-Response-Code") or resp.headers.get("x-response-code")
            if target_code:
                try:
                    report["target_http_status"] = int(target_code)
                except ValueError:
                    report["target_http_status"] = target_code

            report["consumed_units"] = resp.headers.get("X-Units-Consumed") or resp.headers.get("X-Billed-Units")
            report["billed_bandwidth"] = resp.headers.get("X-Billed-Bandwidth") or resp.headers.get("Content-Length")

            body = resp.read().decode("utf-8", errors="replace")
            report["content_length"] = len(body)

            m_title = re.search(r"<title[^>]*>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
            report["title"] = m_title.group(1).replace("\n", " ").strip() if m_title else "Sem <title>"

            report["is_challenge"] = (
                report["target_http_status"] == 403 or
                "Just a moment..." in body or
                "cf-browser-verification" in body
            )

            report["has_view_promotion"] = "view_promotion" in body
            promo_ids = re.findall(r"promotion_id:\s*['\"]([^'\"]+)['\"]", body)
            data_ids = re.findall(r"data-id=['\"]([^'\"]+)['\"]", body)
            all_ids = list(dict.fromkeys(promo_ids + data_ids))
            report["unique_promotion_ids_count"] = len(all_ids)
            report["first_five_ids"] = all_ids[:5]

    except urllib.error.HTTPError as exc:
        report["elapsed_seconds"] = round(time.perf_counter() - start_time, 2)
        report["browserless_http_status"] = exc.code
        report["consumed_units"] = exc.headers.get("X-Units-Consumed") or exc.headers.get("X-Billed-Units")
        report["billed_bandwidth"] = exc.headers.get("X-Billed-Bandwidth")
        try:
            err_body = exc.read().decode("utf-8", errors="replace").strip()
            err_clean = re.sub(r'token=[^&\s"\']+', 'token=REDACTED', err_body)
            err_clean = re.sub(r'Bearer\s+[^\s"\']+', 'Bearer REDACTED', err_clean)
            report["error"] = f"Browserless HTTP {exc.code}: {err_clean if err_clean else exc.reason}"
        except Exception:
            report["error"] = f"Browserless HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        report["elapsed_seconds"] = round(time.perf_counter() - start_time, 2)
        report["error"] = f"{type(exc).__name__}: {exc}"

    report["usage_after"] = _get_account_units(api_key)
    if report["usage_before"] is not None and report["usage_after"] is not None:
        report["usage_delta"] = round(report["usage_after"] - report["usage_before"], 4)

    print("\n" + "=" * 60)
    print("RELATÓRIO SANITIZADO TELEPIZZA RESIDENTIAL:")
    print("=" * 60)
    print(json.dumps(report, indent=2))
    print("=" * 60)


if __name__ == "__main__":
    run_probe()
