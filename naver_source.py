"""
Naver data layer for the Korea Index Tracker.

Naver retired the old finance.naver.com/sise HTML pages in Sep 2026 (entryJongmok
returns 410 Gone; market/group pages 302 to the stock.naver.com JS app). This module
now reads the JSON APIs behind the new site. Group numbers (upjong/theme/group `no`)
are unchanged, so existing index ids stay valid.

All access is anonymous HTTP. Every fetch goes through `_get` (throttle + retry + backoff).

Public API (unchanged):
  list_groups(gtype)            -> [{"no","name"}]            (upjong/theme/group)
  fetch_entry_index(type_code)  -> [{"symbol","name"}]        (KOSPI 200 / 100)
  fetch_market(sosok)           -> [{"symbol","name"}]        (full KOSPI / KOSDAQ)
  fetch_group(gtype, no)        -> [{"symbol","name"}]        (one sector/theme/group)
"""
import time
import requests

import config

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
M_API = "https://m.stock.naver.com/api"                  # index members, full markets
MKT_API = "https://stock.naver.com/api/domestic/market"  # upjong / theme / group
# NB: on MKT_API, `startIdx` is a 0-based PAGE number, not a row offset.

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Referer": "https://stock.naver.com/"})

MARKETS = {0: "KOSPI", 1: "KOSDAQ"}
ENTRY_PAGE = 50     # enrollStocks rejects large page sizes (100 -> HTTP 400)
MARKET_PAGE = 100
GROUP_PAGE = 100
LIST_PAGE = 200     # server max for /list


def _get(url):
    """GET with throttle + retry + exponential backoff. Returns parsed JSON."""
    last = None
    for attempt in range(config.RETRY_MAX):
        try:
            time.sleep(config.THROTTLE_SEC)
            r = _session.get(url, timeout=config.REQUEST_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as e:
            last = repr(e)
        time.sleep(config.THROTTLE_SEC * (config.RETRY_BACKOFF ** (attempt + 1)))
    raise RuntimeError(f"GET failed after {config.RETRY_MAX} attempts ({last}): {url}")


def _collect(fetch_page, code_key, name_key, max_pages=80):
    """Page through a list until a page is empty or yields no NEW codes."""
    out, seen = [], set()
    for page in range(max_pages):
        rows = fetch_page(page)
        new = 0
        for row in rows or []:
            code = str(row.get(code_key) or "").strip()
            if code and code not in seen:
                seen.add(code)
                out.append({"symbol": code, "name": str(row.get(name_key) or "").strip()})
                new += 1
        if not new:
            break
    return out


# ---------------------------------------------------------------------------
# Public fetchers
# ---------------------------------------------------------------------------
def fetch_entry_index(type_code):
    """KOSPI 200 / KOSPI 100 constituents (enrollStocks, 1-based pages)."""
    return _collect(
        lambda p: _get(f"{M_API}/index/{type_code}/enrollStocks?page={p + 1}&pageSize={ENTRY_PAGE}"),
        "itemCode", "stockName")


def fetch_market(sosok):
    """Full market listing. sosok=0 KOSPI, sosok=1 KOSDAQ (by market value)."""
    market = MARKETS[int(sosok)]
    return _collect(
        lambda p: _get(f"{M_API}/stocks/marketValue/{market}?page={p + 1}&pageSize={MARKET_PAGE}")
        .get("stocks", []),
        "itemCode", "stockName")


def fetch_group(gtype, no):
    """One sector/theme/business-group's members."""
    return _collect(
        lambda p: _get(f"{MKT_API}/{gtype}/{no}/stocklist?startIdx={p}"
                       f"&pageSize={GROUP_PAGE}&sortType=quantTop"),
        "itemcode", "itemname")


def list_groups(gtype):
    """All groups of a given type: [{"no","name"}]. gtype in upjong|theme|group."""
    out, seen = [], set()
    for page in range(20):
        rows = _get(f"{MKT_API}/{gtype}/list?startIdx={page}"
                    f"&pageSize={LIST_PAGE}&sortType=changeRate")
        new = [g for g in rows or [] if str(g.get("no")) not in seen]
        if not new:
            break
        for g in new:
            seen.add(str(g["no"]))
            out.append({"no": str(g["no"]), "name": str(g.get("name") or "").strip()})
        if len(rows) < LIST_PAGE:
            break
    return out
