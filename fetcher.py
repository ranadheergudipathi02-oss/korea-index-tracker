"""
Fetcher / orchestrator for the Static Korea Index Tracker.

  build registry (static benchmarks + full markets + discovered sector/group/theme)
  -> fetch each index's members (throttle/retry/backoff in naver_source)
  -> reconcile via diff_engine (snapshot guard, first-run baseline, append changes)
  -> write data/indices.json (registry) + data/meta.json (per-index status + health)

Usage:
  python fetcher.py                 # full run (all allow-listed categories)
  python fetcher.py --quick         # static indices + first 3 sectors (smoke test)
  python fetcher.py --only kospi-200,kospi-100
  python fetcher.py --max-groups 5  # cap groups per category (testing)
"""
import krx_env  # utf-8 console
import argparse
import json
import os
import traceback
from datetime import datetime, timedelta, timezone

import config
import naver_source as ns
import diff_engine

KST = timezone(timedelta(hours=9))


def log(m):
    print(m, flush=True)


def build_registry(max_groups=None, quick=False):
    """Return the list of index descriptors to fetch this run."""
    registry = list(config.STATIC_INDICES)
    for gtype, category, prefix, enabled in config.GROUP_CATEGORIES:
        if not enabled:
            continue
        try:
            groups = ns.list_groups(gtype)
        except Exception as e:
            log(f"  ! could not list groups type={gtype}: {e!r}")
            continue
        if quick and category != "sector":
            continue
        if quick:
            groups = groups[:3]
        elif max_groups:
            groups = groups[:max_groups]
        for g in groups:
            registry.append({
                "id": f"{prefix}-{g['no']}", "name": g["name"], "category": category,
                "method": "group", "gtype": gtype, "no": g["no"],
            })
    return registry


def fetch_members(idx):
    method = idx["method"]
    if method == "entry":
        return ns.fetch_entry_index(idx["type"])
    if method == "market":
        return ns.fetch_market(idx["sosok"])
    if method == "group":
        return ns.fetch_group(idx["gtype"], idx["no"])
    raise ValueError(f"unknown method {method}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", default=None, help="comma-separated index ids")
    ap.add_argument("--max-groups", type=int, default=None)
    args = ap.parse_args()

    started = datetime.now(KST)
    detect_date = started.strftime("%Y-%m-%d")
    log(f"Korea Index Tracker fetch | {started.isoformat()} | detect_date={detect_date}")

    registry = build_registry(max_groups=args.max_groups, quick=args.quick)
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        registry = [i for i in registry if i["id"] in wanted]
    log(f"  registry: {len(registry)} indices to fetch")

    os.makedirs(config.DATA, exist_ok=True)
    # Persist the registry (frontend directory). Strip transient fetch params.
    with open(config.INDICES, "w", encoding="utf-8") as f:
        json.dump(
            {"indices": [{"id": i["id"], "name": i["name"], "category": i["category"]}
                         for i in registry],
             "unavailable": config.UNAVAILABLE},
            f, ensure_ascii=False, indent=1, sort_keys=True)

    results = {}
    counts = {"initial": 0, "changed": 0, "unchanged": 0, "guarded": 0, "error": 0}
    for n, idx in enumerate(registry, 1):
        try:
            members = fetch_members(idx)
            status = diff_engine.reconcile(
                idx["id"], idx["name"], idx["category"], members, detect_date)
        except Exception as e:
            status = {"status": "error", "reason": repr(e)}
            log(f"  [{n}/{len(registry)}] {idx['id']:18} ERROR {e!r}")
            traceback.print_exc()
        st = status["status"]
        counts[st] = counts.get(st, 0) + 1
        results[idx["id"]] = status
        if st in ("guarded", "error", "initial", "changed"):
            log(f"  [{n}/{len(registry)}] {idx['id']:18} {st:9} {status.get('count','')} "
                f"{status.get('reason','')}")

    finished = datetime.now(KST)
    # Health: unhealthy if many indices failed/guarded (silent-block signal).
    bad = counts["guarded"] + counts["error"]
    total = len(registry)
    unhealthy = total > 0 and (bad / total) > 0.5
    meta = {
        "last_run_kst": started.isoformat(),
        "finished_kst": finished.isoformat(),
        "duration_sec": round((finished - started).total_seconds(), 1),
        "detect_date": detect_date,
        "source": "naver_finance",
        "total_indices": total,
        "counts": counts,
        "unhealthy": unhealthy,
        "results": results,
    }
    with open(config.META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1, sort_keys=True)

    log(f"\n  DONE in {meta['duration_sec']}s | {counts} | unhealthy={unhealthy}")
    return meta


if __name__ == "__main__":
    main()
