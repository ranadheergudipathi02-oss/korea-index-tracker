"""
Naver Finance data layer for the Korea Index Tracker.

All access is anonymous HTTP against finance.naver.com. Pages are EUC-KR(cp949);
lists are paginated. Every fetch goes through `_get` (throttle + retry + backoff).

Public API:
  list_groups(gtype)            -> [{"no","name"}]            (sectors/themes/groups)
  fetch_entry_index(type_code)  -> [{"symbol","name"}]        (KOSPI 200 / 100)
  fetch_market(sosok)           -> [{"symbol","name"}]        (full KOSPI / KOSDAQ)
  fetch_group(gtype, no)        -> [{"symbol","name"}]        (one sector/theme/group)
"""
import re
import time
import requests

import config

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
BASE = "https://finance.naver.com/sise"

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Referer": "https://finance.naver.com/sise/"})

# /item/main.naver?code=005930">삼성전자</a>
_ROW = re.compile(r'/item/main\.naver\?code=(\d{6})"[^>]*>\s*([^<]+?)\s*</a>')


def _get(url):
    """GET with throttle + retry + exponential backoff. Returns EUC-KR-decoded text."""
    last = None
    for attempt in range(config.RETRY_MAX):
        try:
            time.sleep(config.THROTTLE_SEC)
            r = _session.get(url, timeout=config.REQUEST_TIMEOUT)
            r.encoding = "euc-kr"
            if r.status_code == 200 and r.text:
                return r.text
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last = repr(e)
        # backoff before next attempt
        time.sleep(config.THROTTLE_SEC * (config.RETRY_BACKOFF ** (attempt + 1)))
    raise RuntimeError(f"GET failed after {config.RETRY_MAX} attempts ({last}): {url}")


def _members_from(html):
    """Parse (code,name) rows from a Naver list page, de-duped, order-preserving."""
    out, seen = [], set()
    for code, name in _ROW.findall(html):
        if code not in seen:
            seen.add(code)
            out.append({"symbol": code, "name": name.strip()})
    return out


def _walk(url_for_page, max_pages=80):
    """Walk paginated list pages until a page yields no NEW codes. Robust whether or
    not the endpoint honors the page param (if ignored, page 1 already has all)."""
    all_m, seen = [], set()
    for page in range(1, max_pages + 1):
        html = _get(url_for_page(page))
        page_m = _members_from(html)
        new = [m for m in page_m if m["symbol"] not in seen]
        if not new:
            break
        for m in new:
            seen.add(m["symbol"])
        all_m.extend(new)
    return all_m


# ---------------------------------------------------------------------------
# Public fetchers
# ---------------------------------------------------------------------------
def fetch_entry_index(type_code):
    """KOSPI 200 / KOSPI 100 style indices (entryJongmok, 10/page)."""
    return _walk(lambda p: f"{BASE}/entryJongmok.naver?type={type_code}&page={p}")


def fetch_market(sosok):
    """Full market membership. sosok=0 KOSPI, sosok=1 KOSDAQ (market_sum, 50/page)."""
    return _walk(lambda p: f"{BASE}/sise_market_sum.naver?sosok={sosok}&page={p}")


def fetch_group(gtype, no):
    """One sector/theme/business-group's members (sise_group_detail)."""
    return _walk(lambda p: f"{BASE}/sise_group_detail.naver?type={gtype}&no={no}&page={p}")


def list_groups(gtype):
    """All groups of a given type: [{"no","name"}]. gtype in upjong|theme|group."""
    html = _get(f"{BASE}/sise_group.naver?type={gtype}")
    pat = re.compile(
        rf'sise_group_detail\.naver\?type={gtype}&no=(\d+)"[^>]*>\s*([^<]+?)\s*</a>')
    out, seen = [], set()
    for no, name in pat.findall(html):
        if no not in seen:
            seen.add(no)
            out.append({"no": no, "name": name.strip()})
    return out
