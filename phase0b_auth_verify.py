"""
Phase 0b — Authenticated KRX verification (the piece that needs a real account).

Confirms the full chain works from THIS IP with login:
  - .env -> KRX_ID/KRX_PW reach pykrx at import time
  - pykrx logs into data.krx.co.kr successfully
  - full index list (KOSPI / KOSDAQ / KRX) + name resolution
  - constituents for KOSPI 200, KOSDAQ 150, KRX 300 + member name resolution

Run:  python phase0b_auth_verify.py
Writes artifacts to ./phase0_out/.
"""
import krx_env  # MUST be first: loads .env + utf-8 console BEFORE pykrx import
import json
import os
import time
from datetime import datetime, timedelta, timezone

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phase0_out")
os.makedirs(OUT, exist_ok=True)
KST = timezone(timedelta(hours=9))


def log(m):
    print(m, flush=True)


def recent_business_days(n=10):
    d = datetime.now(KST).date()
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return out


def main():
    log(f"Phase 0b auth verify | {datetime.now(KST).isoformat()}")

    if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
        log("FATAL: KRX_ID / KRX_PW not found. Create .env from .env.example first.")
        raise SystemExit(2)
    log(f"  KRX_ID present: {os.environ['KRX_ID'][:3]}***  (pw hidden)")

    # pykrx logs in at import (prints '로그인 완료' on success).
    from pykrx import stock
    from pykrx.website.comm import webio
    sess = webio.get_session()
    authed = bool(sess and getattr(sess, "is_authenticated", False))
    log(f"  pykrx session authenticated: {authed}")
    if not authed:
        log("  WARNING: session not authenticated — login likely failed (check creds).")

    report = {"authenticated": authed, "index_lists": {}, "headline": {}, "errors": []}

    # working date
    working = None
    for d in recent_business_days(10):
        try:
            if stock.get_index_ticker_list(date=d, market="KOSPI"):
                working = d
                break
        except Exception as e:
            log(f"    {d}: {e!r}")
        time.sleep(0.5)
    report["working_date"] = working
    log(f"  working date: {working}")
    if not working:
        report["errors"].append("no working date — auth or endpoint still failing")
        with open(os.path.join(OUT, "phase0b_report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        log("  ABORT: data calls still failing even after login attempt.")
        raise SystemExit(1)

    name_to_ticker = {}
    for market in ("KOSPI", "KOSDAQ", "KRX"):
        try:
            codes = stock.get_index_ticker_list(date=working, market=market)
            named = []
            for c in codes:
                try:
                    nm = stock.get_index_ticker_name(c).strip()
                except Exception as e:
                    nm = f"<err {e!r}>"
                named.append({"ticker": c, "name": nm})
                name_to_ticker.setdefault(nm, c)
                time.sleep(0.03)
            report["index_lists"][market] = named
            log(f"  {market}: {len(named)} indices")
            with open(os.path.join(OUT, f"index_list_{market}.txt"), "w", encoding="utf-8") as f:
                for it in named:
                    f.write(f"{it['ticker']}\t{it['name']}\n")
        except Exception as e:
            report["errors"].append(f"{market} list: {e!r}")
            log(f"  {market} list FAILED: {e!r}")
        time.sleep(0.6)

    # headline indices by name (loose, space-insensitive match)
    def resolve(target):
        t = target.replace(" ", "")
        for nm, tk in name_to_ticker.items():
            if nm.replace(" ", "") == t:
                return tk
        return None

    for tname in ("KOSPI 200", "KOSDAQ 150", "KRX 300"):
        tk = resolve(tname)
        entry = {"ticker": tk}
        if not tk:
            entry["error"] = "not resolved from index lists"
            log(f"  [{tname}] NOT resolved")
        else:
            try:
                members = stock.get_index_portfolio_deposit_file(working, tk)
                sample = []
                for s in members[:5]:
                    try:
                        sample.append({"symbol": s, "name": stock.get_market_ticker_name(s)})
                    except Exception as e:
                        sample.append({"symbol": s, "name": f"<err {e!r}>"})
                    time.sleep(0.03)
                entry.update({"member_count": len(members), "sample": sample})
                log(f"  [{tname}] ticker={tk} members={len(members)} sample={[x['name'] for x in sample[:3]]}")
            except Exception as e:
                entry["error"] = repr(e)
                log(f"  [{tname}] constituents FAILED: {e!r}")
        report["headline"][tname] = entry
        time.sleep(0.8)

    report["verdict"] = (
        "PASS" if authed and report["headline"].get("KOSPI 200", {}).get("member_count")
        else "FAIL"
    )
    with open(os.path.join(OUT, "phase0b_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"\n  VERDICT: {report['verdict']}")
    log(f"  artifacts in {OUT}")


if __name__ == "__main__":
    main()
