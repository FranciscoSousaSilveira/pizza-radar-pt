"""Sonda de diagnóstico multiplataforma para Domino's e Telepizza.

Executa em matriz de runners (Ubuntu, Windows, macOS) para mapear
se algum pool de IPs tem acesso livre aos sites oficiais.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    return "Nenhum <title> encontrado"


def probe_http(url: str, method: str = "GET", data: bytes | None = None, extra_headers: dict | None = None) -> dict:
    headers = dict(_HEADERS)
    if extra_headers:
        headers.update(extra_headers)

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    res = {
        "url": url,
        "method": method,
        "status": None,
        "length": 0,
        "title": "",
        "selectors_found": [],
        "error": None,
    }

    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            res["status"] = resp.status
            content = resp.read()
            res["length"] = len(content)
            text = content.decode("utf-8", errors="replace")
            res["title"] = _extract_title(text)

            # Procura seletores esperados
            if "combo-id" in text:
                res["selectors_found"].append("combo-id")
            if "offer-title" in text:
                res["selectors_found"].append("offer-title")
            if "data-id=" in text:
                res["selectors_found"].append("data-id")
            if "view_promotion" in text:
                res["selectors_found"].append("view_promotion")
            if "combos" in text:
                res["selectors_found"].append("combos")

    except urllib.error.HTTPError as exc:
        res["status"] = exc.code
        res["error"] = f"HTTP {exc.code}: {exc.reason}"
        try:
            body = exc.read().decode("utf-8", errors="replace")
            res["title"] = _extract_title(body)
        except Exception:
            pass
    except Exception as exc:
        res["error"] = f"{type(exc).__name__}: {exc}"

    return res


def probe_telepizza_scapi() -> dict:
    res = {
        "url": "SCAPI e6dubte9.api.commercecloud.salesforce.com",
        "method": "PKCE+GET",
        "status": None,
        "length": 0,
        "title": "SCAPI Shopper Promotions",
        "selectors_found": [],
        "error": None,
    }
    try:
        short_code = "e6dubte9"
        org_id = "f_ecom_bktv_prd"
        site_id = "TelepizzaPT"
        client_id = "33caf917-7f3d-4a33-b78e-75424c3e4985"

        code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8").rstrip("=")
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest()).decode("utf-8").rstrip("=")
        redirect_uri = "http://localhost:3000/callback"

        params = urllib.parse.urlencode({
            "client_id": client_id,
            "channel_id": site_id,
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "redirect_uri": redirect_uri,
            "hint": "guest"
        })
        auth_url = f"https://{short_code}.api.commercecloud.salesforce.com/shopper/auth/v1/organizations/{org_id}/oauth2/authorize?{params}"

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(NoRedirect)
        try:
            r = opener.open(auth_url)
            loc = r.headers.get("Location")
        except urllib.error.HTTPError as e:
            loc = e.headers.get("Location")

        parsed_loc = urllib.parse.urlparse(loc)
        qs = urllib.parse.parse_qs(parsed_loc.query)
        auth_code = qs["code"][0]

        token_url = f"https://{short_code}.api.commercecloud.salesforce.com/shopper/auth/v1/organizations/{org_id}/oauth2/token"
        token_data = urllib.parse.urlencode({
            "grant_type": "authorization_code_pkce",
            "client_id": client_id,
            "code": auth_code,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "channel_id": site_id
        }).encode("utf-8")

        t_req = urllib.request.Request(token_url, data=token_data, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0"
        })
        with urllib.request.urlopen(t_req) as t_resp:
            token = json.loads(t_resp.read().decode())["access_token"]

        promo_url = f"https://{short_code}.api.commercecloud.salesforce.com/pricing/shopper-promotions/v1/organizations/{org_id}/promotions?siteId={site_id}&ids=2x1_MedFam,3PMENOSTK"
        p_req = urllib.request.Request(promo_url, headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0"
        })
        with urllib.request.urlopen(p_req) as p_resp:
            res["status"] = p_resp.status
            body = p_resp.read()
            res["length"] = len(body)
            data = json.loads(body.decode())
            if len(data.get("data", [])) > 0:
                res["selectors_found"].append(f"promotions_returned:{len(data.get('data', []))}")
    except Exception as exc:
        res["error"] = f"{type(exc).__name__}: {exc}"

    return res


def main():
    current_os = f"{platform.system()} {platform.release()} ({platform.machine()})"
    print("=" * 70)
    print(f"MATRIZ DE EGRESS — RELATÓRIO DO RUNNER: {current_os}")
    print("=" * 70)

    # 1. Domino's Homepage
    dom_home = probe_http("https://www.dominospizza.pt/")
    # 2. Domino's Endpoint POST
    dom_post_data = urllib.parse.urlencode({
        "get_menu": "140",
        "time": "NOW",
        "delivery_method": "D"
    }).encode("utf-8")
    dom_post = probe_http(
        "https://www.dominospizza.pt/ajax/order.php",
        method="POST",
        data=dom_post_data,
        extra_headers={"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}
    )
    # 3. Telepizza app.telepizza.pt
    tp_app = probe_http("https://app.telepizza.pt/promocoes")
    # 4. Telepizza www.telepizza.pt
    tp_www = probe_http("https://www.telepizza.pt/promocoes")
    # 5. Telepizza SCAPI
    tp_scapi = probe_telepizza_scapi()

    all_probes = [
        ("Domino's Homepage", dom_home),
        ("Domino's Endpoint (ajax/order.php)", dom_post),
        ("Telepizza app.telepizza.pt/promocoes", tp_app),
        ("Telepizza www.telepizza.pt/promocoes", tp_www),
        ("Telepizza Salesforce SCAPI", tp_scapi),
    ]

    for label, r in all_probes:
        print(f"\n--- {label} ---")
        print(f"  OS: {current_os}")
        print(f"  URL: {r['url']} ({r['method']})")
        print(f"  Status HTTP: {r['status']}")
        print(f"  Tamanho: {r['length']} bytes")
        print(f"  Título: {r['title']}")
        print(f"  Seletores detetados: {r['selectors_found']}")
        if r['error']:
            print(f"  Erro: {r['error']}")

    print("\n" + "=" * 70)
    print("FIM DO RELATÓRIO DO RUNNER")
    print("=" * 70)


if __name__ == "__main__":
    main()
