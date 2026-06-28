"""
Phase 0c — Naver Finance source discovery (the active data source).

Maps exactly what we can build the tracker from, anonymously, from this IP:
  1. Benchmark index 'type' codes that return constituents (entryJongmok)
  2. Full KOSPI / KOSDAQ market member lists (sise_market_sum, sosok=0/1)
  3. Sector (업종/upjong) group list  + sample membership
  4. Theme group list
Handles EUC-KR(cp949) decoding + pagination. Writes ./phase0_out/naver_*.json.
"""
import krx_env  # utf-8 console
import json
import os
import re
import time
import requests

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phase0_out")
os.makedirs(OUT, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Referer": "https://finance.naver.com/sise/"})


def log(m):
    print(m, flush=True)


def get(url):
    r = S.get(url, timeout=20)
    r.encoding = "euc-kr"  # Naver Finance is EUC-KR
    return r.text


def codes_and_names(html):
    """Extract (code, name) pairs from a Naver list table row pattern."""
    # rows look like: /item/main.naver?code=005930">삼성전자</a>
    pairs = re.findall(r'/item/main\.naver\?code=(\d{6})"[^>]*>\s*([^<]+?)\s*</a>', html)
    # de-dup preserving order
    seen, out = set(), []
    for c, n in pairs:
        if c not in seen:
            seen.add(c)
            out.append({"symbol": c, "name": n.strip()})
    return out


# ---------------------------------------------------------------------------
# 1. Benchmark index type codes via entryJongmok
# ---------------------------------------------------------------------------
def discover_benchmark_types():
    log("\n=== 1. BENCHMARK index 'type' codes (entryJongmok) ===")
    candidates = [
        "KPI200", "KPI100", "KPI50", "KOSPI", "KOSPI100", "KOSPI50",
        "KOSDAQ", "KOSDAQ150", "KSQ150", "KQ150", "KRX100", "KRX300",
        "KPS", "FLI", "KRXBNK", "KRXIT", "KRXHC",
    ]
    found = {}
    for t in candidates:
        try:
            html = get(f"https://finance.naver.com/sise/entryJongmok.naver?type={t}&page=1")
            members = codes_and_names(html)
            # detect total pages
            pages = re.findall(r"page=(\d+)", html)
            maxpage = max((int(p) for p in pages), default=1)
            found[t] = {"page1_members": len(members), "max_page_link": maxpage,
                        "sample": [m["name"] for m in members[:3]]}
            tag = "OK" if members else "--"
            log(f"  [{tag}] type={t:10} page1={len(members):2d} maxpage~{maxpage} {found[t]['sample']}")
        except Exception as e:
            found[t] = {"error": repr(e)}
            log(f"  [ER] type={t}: {e!r}")
        time.sleep(0.4)
    return found


def walk_entryjongmok(t, max_pages=40):
    """Pull ALL members of an entryJongmok index across pages."""
    all_m, seen = [], set()
    for p in range(1, max_pages + 1):
        html = get(f"https://finance.naver.com/sise/entryJongmok.naver?type={t}&page={p}")
        ms = codes_and_names(html)
        new = [m for m in ms if m["symbol"] not in seen]
        if not new:
            break
        for m in new:
            seen.add(m["symbol"])
        all_m.extend(new)
        time.sleep(0.3)
    return all_m


# ---------------------------------------------------------------------------
# 2. Full KOSPI / KOSDAQ market member lists
# ---------------------------------------------------------------------------
def discover_full_market(sosok, label):
    log(f"\n=== 2. FULL {label} (sise_market_sum sosok={sosok}) ===")
    all_m, seen = [], set()
    for p in range(1, 60):
        html = get(f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={p}")
        ms = codes_and_names(html)
        new = [m for m in ms if m["symbol"] not in seen]
        if not new:
            break
        for m in new:
            seen.add(m["symbol"])
        all_m.extend(new)
        time.sleep(0.25)
    log(f"  {label}: {len(all_m)} members (sample {[m['name'] for m in all_m[:3]]})")
    return all_m


# ---------------------------------------------------------------------------
# 3 + 4. Sector (upjong) and theme group lists
# ---------------------------------------------------------------------------
def discover_groups(gtype, label):
    log(f"\n=== {label} groups (sise_group type={gtype}) ===")
    html = get(f"https://finance.naver.com/sise/sise_group.naver?type={gtype}")
    # links: sise_group_detail.naver?type=upjong&no=NN">NAME</a>
    items = re.findall(
        rf'sise_group_detail\.naver\?type={gtype}&no=(\d+)"[^>]*>\s*([^<]+?)\s*</a>', html)
    seen, groups = set(), []
    for no, name in items:
        if no not in seen:
            seen.add(no)
            groups.append({"no": no, "name": name.strip()})
    log(f"  {label}: {len(groups)} groups")
    # sample one group's membership
    sample_members = []
    if groups:
        ghtml = get(f"https://finance.naver.com/sise/sise_group_detail.naver?type={gtype}&no={groups[0]['no']}")
        sample_members = codes_and_names(ghtml)
        log(f"    sample '{groups[0]['name']}' -> {len(sample_members)} members {[m['name'] for m in sample_members[:3]]}")
    return {"groups": groups, "sample_group": groups[0] if groups else None,
            "sample_member_count": len(sample_members)}


def main():
    report = {}
    report["benchmark_types"] = discover_benchmark_types()

    # Deep-pull the headline indices that worked, to get true member counts.
    report["headline_full"] = {}
    for t in ("KPI200", "KPI100", "KPI50", "KOSDAQ150", "KSQ150"):
        info = report["benchmark_types"].get(t, {})
        if info.get("page1_members"):
            mem = walk_entryjongmok(t)
            report["headline_full"][t] = {"count": len(mem), "members": mem}
            log(f"  FULL {t}: {len(mem)} members")

    report["full_KOSPI"] = discover_full_market(0, "KOSPI")
    report["full_KOSDAQ"] = discover_full_market(1, "KOSDAQ")
    report["sectors"] = discover_groups("upjong", "Sector(업종)")
    report["themes"] = discover_groups("theme", "Theme(테마)")
    report["business_groups"] = discover_groups("group", "그룹사")

    with open(os.path.join(OUT, "naver_discovery.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    log("\n=== SUMMARY ===")
    log(f"  full KOSPI members:   {len(report['full_KOSPI'])}")
    log(f"  full KOSDAQ members:  {len(report['full_KOSDAQ'])}")
    for t, v in report["headline_full"].items():
        log(f"  {t}: {v['count']}")
    log(f"  sector groups:   {len(report['sectors']['groups'])}")
    log(f"  theme groups:    {len(report['themes']['groups'])}")
    log(f"  business groups: {len(report['business_groups']['groups'])}")
    log(f"\n  artifact: {os.path.join(OUT, 'naver_discovery.json')}")


if __name__ == "__main__":
    main()
