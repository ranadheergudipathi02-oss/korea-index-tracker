"""
Build the static-site summary from the JSON storage.

Reads data/current/*.json + data/changes.jsonl + data/meta.json and writes
data/summary.json — a single payload the frontend loads for: the index directory
(with member counts), the global recent-changes feed, and the stock->indices
reverse lookup. Per-index member detail is still loaded on demand from
current/<id>.json, so summary.json stays small-ish.
"""
import krx_env  # utf-8 console
import glob
import json
import os
from datetime import datetime, timedelta, timezone

import config

KST = timezone(timedelta(hours=9))

CATEGORY_LABELS = [
    ("broad", "Broad / Benchmark"),
    ("sector", "Sector (업종)"),
    ("group", "Business Group (그룹사)"),
    ("theme", "Theme (테마)"),
]
RECENT_LIMIT = 100


def main():
    indices, stock_index, stock_names = [], {}, {}

    for path in sorted(glob.glob(os.path.join(config.CURRENT, "*.json"))):
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        idx_id = d["index"]
        indices.append({"id": idx_id, "name": d["name"],
                        "category": d["category"], "count": len(d["members"])})
        for m in d["members"]:
            sym = m["symbol"]
            stock_index.setdefault(sym, []).append(idx_id)
            stock_names.setdefault(sym, m["name"])

    indices.sort(key=lambda i: (i["category"], -i["count"], i["name"]))
    for sym in stock_index:
        stock_index[sym].sort()

    # recent changes: last RECENT_LIMIT records, newest first
    recent = []
    if os.path.exists(config.CHANGES):
        with open(config.CHANGES, "r", encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        for line in lines[-RECENT_LIMIT:]:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            recent.append({
                "date": r["date"], "index": r["index"], "name": r.get("name"),
                "category": r.get("category"), "type": r["type"],
                "added": r.get("added", []), "removed": r.get("removed", []),
                "count": r.get("count"),
            })
    recent.reverse()

    meta = {}
    if os.path.exists(config.META):
        with open(config.META, "r", encoding="utf-8") as f:
            meta = json.load(f)

    summary = {
        "generated_kst": datetime.now(KST).isoformat(),
        "source": "naver_finance",
        "detect_date": meta.get("detect_date"),
        "last_run_kst": meta.get("last_run_kst"),
        "counts": meta.get("counts", {}),
        "unhealthy": meta.get("unhealthy", False),
        "categories": [{"key": k, "label": l} for k, l in CATEGORY_LABELS],
        "total_indices": len(indices),
        "total_stocks": len(stock_index),
        "indices": indices,
        "unavailable": config.UNAVAILABLE,
        "recent_changes": recent,
        "stock_index": stock_index,
        "stock_names": stock_names,
    }
    with open(os.path.join(config.DATA, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, separators=(",", ":"))
    print(f"summary.json: {len(indices)} indices, {len(stock_index)} stocks, "
          f"{len(recent)} recent changes")


if __name__ == "__main__":
    main()
