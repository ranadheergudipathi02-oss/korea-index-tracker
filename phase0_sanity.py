"""
Phase 0 — Sanity Test for the Static Korea Index Tracker.

Resolves the real unknowns before any fetcher is built:
  (a) reachability of pykrx / data.krx.co.kr from THIS machine's IP
  (b) pull headline indices (KOSPI 200, KOSDAQ 150, KRX 300) + name resolution
  (c) dump the FULL KRX index list (KOSPI + KOSDAQ) to build the allow-list
  (d) decide pykrx-vs-raw-HTTP per source

Pure stdlib + pykrx. Writes machine-readable artifacts to ./phase0_out/.
Does NOT write any of the real storage layout (current/, changes.jsonl, meta.json).
"""
import json
import os
import ssl
import sys
import time
import socket
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phase0_out")
os.makedirs(OUT, exist_ok=True)

KST = timezone(timedelta(hours=9))


def log(msg):
    print(msg, flush=True)


def recent_business_days(n=10):
    """Yield YYYYMMDD strings going backward from today (KST), skipping weekends."""
    d = datetime.now(KST).date()
    out = []
    while len(out) < n:
        if d.weekday() < 5:  # Mon-Fri
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# (a) Raw reachability + latency to data.krx.co.kr
# ---------------------------------------------------------------------------
def check_raw_reachability():
    log("\n=== (a) RAW REACHABILITY: data.krx.co.kr ===")
    result = {"host": "data.krx.co.kr", "http_get": None, "json_post": None}

    # Simple GET to the landing page
    t0 = time.time()
    try:
        req = urllib.request.Request(
            "http://data.krx.co.kr/",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        r = urllib.request.urlopen(req, timeout=25)
        ms = round((time.time() - t0) * 1000)
        result["http_get"] = {"status": r.status, "latency_ms": ms}
        log(f"  GET /            -> {r.status}  ({ms} ms)")
    except Exception as e:
        result["http_get"] = {"error": repr(e)}
        log(f"  GET /            -> ERROR {e!r}")

    # The real data endpoint: POST bldAttendant/getJsonData.cmd
    # bld MDCSTAT00301 = index list under the "indices" tree (probe one known bld).
    # We probe a stable index-constituent bld to confirm JSON POST works.
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    payload = {
        # PDF deposit file (index constituents) for KOSPI 200 (idxIndCd 028 / indTpCd 1)
        "bld": "dbms/MDC/STAT/standard/MDCSTAT00601",
        "locale": "en",
        "indTpCd": "1",
        "idxIndCd": "028",
        "trdDd": recent_business_days(1)[0],
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false",
    }
    t0 = time.time()
    try:
        data = urllib.parse.urlencode(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
        )
        r = urllib.request.urlopen(req, timeout=25)
        ms = round((time.time() - t0) * 1000)
        body = r.read().decode("utf-8", "replace")
        try:
            j = json.loads(body)
            keys = list(j.keys())
            # find the first list-valued key
            rows = next((j[k] for k in keys if isinstance(j[k], list)), [])
            result["json_post"] = {
                "status": r.status,
                "latency_ms": ms,
                "top_keys": keys,
                "row_count": len(rows),
                "sample_row": rows[0] if rows else None,
            }
            log(f"  POST getJsonData -> {r.status}  ({ms} ms)  keys={keys}  rows={len(rows)}")
            if rows:
                log(f"    sample row: {rows[0]}")
        except json.JSONDecodeError:
            result["json_post"] = {"status": r.status, "latency_ms": ms,
                                   "not_json_first200": body[:200]}
            log(f"  POST getJsonData -> {r.status} but NON-JSON: {body[:120]!r}")
    except Exception as e:
        result["json_post"] = {"error": repr(e)}
        log(f"  POST getJsonData -> ERROR {e!r}")

    return result


# ---------------------------------------------------------------------------
# pykrx checks
# ---------------------------------------------------------------------------
def check_pykrx():
    log("\n=== (b)+(c) PYKRX ===")
    out = {"import_ok": False, "version": None, "working_date": None,
           "index_lists": {}, "headline": {}, "errors": []}
    try:
        import importlib.metadata as m
        out["version"] = m.version("pykrx")
        from pykrx import stock
        out["import_ok"] = True
        log(f"  pykrx import OK (v{out['version']})")
    except Exception as e:
        out["errors"].append(f"import: {e!r}")
        log(f"  pykrx IMPORT FAILED: {e!r}")
        return out

    # Find a working business day where the index list is non-empty.
    working_date = None
    for d in recent_business_days(10):
        try:
            lst = stock.get_index_ticker_list(date=d, market="KOSPI")
            if lst:
                working_date = d
                log(f"  working business date = {d} (KOSPI index list len={len(lst)})")
                break
        except Exception as e:
            log(f"    {d}: {e!r}")
        time.sleep(0.6)
    out["working_date"] = working_date
    if not working_date:
        out["errors"].append("no working date found in last 10 business days")
        log("  COULD NOT find a working date — aborting pykrx index pulls")
        return out

    # (c) Full index list for both markets, with names.
    for market in ("KOSPI", "KOSDAQ"):
        try:
            codes = stock.get_index_ticker_list(date=working_date, market=market)
            named = []
            for c in codes:
                try:
                    nm = stock.get_index_ticker_name(c)
                except Exception as e:
                    nm = f"<name-error {e!r}>"
                named.append({"code": c, "name": nm})
                time.sleep(0.05)
            out["index_lists"][market] = named
            log(f"  {market}: {len(named)} indices")
        except Exception as e:
            out["errors"].append(f"index_list {market}: {e!r}")
            log(f"  {market} index list FAILED: {e!r}")
        time.sleep(0.6)

    # (b) Headline indices: resolve code by name match, then pull constituents.
    targets = {
        "KOSPI 200": "KOSPI",
        "KOSDAQ 150": "KOSDAQ",
        "KRX 300": "KRX",  # KRX-wide indices appear under KOSPI market list in pykrx
    }
    # Build a combined name->code map from what we fetched (+ KRX market).
    name_to_code = {}
    for market in ("KOSPI", "KOSDAQ"):
        for item in out["index_lists"].get(market, []):
            name_to_code[item["name"].strip()] = (item["code"], market)
    # KRX market list (KRX 100/300 etc.)
    try:
        for c in stock.get_index_ticker_list(date=working_date, market="KRX"):
            try:
                nm = stock.get_index_ticker_name(c).strip()
            except Exception:
                nm = c
            name_to_code.setdefault(nm, (c, "KRX"))
        out["index_lists"]["KRX"] = [
            {"code": c, "name": stock.get_index_ticker_name(c)}
            for c in stock.get_index_ticker_list(date=working_date, market="KRX")
        ]
        log(f"  KRX: {len(out['index_lists']['KRX'])} indices")
    except Exception as e:
        out["errors"].append(f"KRX list: {e!r}")
        log(f"  KRX index list FAILED: {e!r}")

    for tname in targets:
        code = None
        # exact, then loose match
        if tname in name_to_code:
            code = name_to_code[tname][0]
        else:
            for nm, (c, mk) in name_to_code.items():
                if nm.replace(" ", "") == tname.replace(" ", ""):
                    code = c
                    break
        entry = {"resolved_code": code}
        if not code:
            entry["error"] = "code not resolved from name map"
            log(f"  [{tname}] code NOT resolved")
            out["headline"][tname] = entry
            continue
        try:
            members = stock.get_index_portfolio_deposit_file(code, date=working_date)
            sample = []
            for sym in members[:5]:
                try:
                    nm = stock.get_market_ticker_name(sym)
                except Exception as e:
                    nm = f"<name-err {e!r}>"
                sample.append({"symbol": sym, "name": nm})
                time.sleep(0.05)
            entry.update({"member_count": len(members), "sample": sample})
            log(f"  [{tname}] code={code}  members={len(members)}  sample={sample[:3]}")
        except Exception as e:
            entry["error"] = repr(e)
            log(f"  [{tname}] constituents FAILED: {e!r}")
        out["headline"][tname] = entry
        time.sleep(0.8)

    return out


def main():
    started = datetime.now(KST).isoformat()
    log(f"Phase 0 sanity test  |  {started}  |  host={socket.gethostname()}")
    report = {"started_kst": started}

    report["raw_reachability"] = check_raw_reachability()
    report["pykrx"] = check_pykrx()

    # Decision (d): which source per call.
    pk = report["pykrx"]
    raw = report["raw_reachability"]
    decision = {
        "pykrx_usable": bool(pk.get("import_ok") and pk.get("working_date")
                             and pk.get("index_lists")),
        "raw_http_usable": bool(isinstance(raw.get("json_post"), dict)
                                and raw["json_post"].get("row_count", 0) > 0),
    }
    decision["primary"] = "pykrx" if decision["pykrx_usable"] else (
        "raw_http" if decision["raw_http_usable"] else "NONE-REACHABLE")
    decision["fallback"] = "raw_http" if decision["raw_http_usable"] else "none"
    report["decision"] = decision

    with open(os.path.join(OUT, "phase0_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Human-readable index list dumps for allow-list building.
    for market, items in pk.get("index_lists", {}).items():
        with open(os.path.join(OUT, f"index_list_{market}.txt"), "w", encoding="utf-8") as f:
            for it in items:
                f.write(f"{it['code']}\t{it['name']}\n")

    log("\n=== DECISION (d) ===")
    log(json.dumps(decision, indent=2))
    log(f"\nArtifacts written to: {OUT}")
    log("  - phase0_report.json (full)")
    log("  - index_list_KOSPI.txt / index_list_KOSDAQ.txt / index_list_KRX.txt")


if __name__ == "__main__":
    main()
