"""
Diff engine + correctness guards for the Korea Index Tracker.

Per index, reconcile a freshly-fetched member list against the last snapshot in
current/<id>.json:

  - Snapshot guard: if the new fetch is empty OR shrinks more than
    GUARD_DROP_FRACTION vs the previous snapshot, SKIP the write+diff and report
    a guarded/failed status (primary corruption guard). The old snapshot is kept.
  - First-run baseline: no previous file => write current/ and emit one
    {type:"initial"} change, no add/remove diff.
  - Change: membership changed => write current/ and append a {type:"change"}
    record with added/removed.

changes.jsonl is append-only and written ONLY on a detected diff.
current/<id>.json carries NO timestamps (avoids git churn); members are sorted by
symbol so reordering never produces a spurious diff.
"""
import json
import os

import config


def _read_current(index_id):
    path = os.path.join(config.CURRENT, f"{index_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_current(index_id, name, category, members):
    os.makedirs(config.CURRENT, exist_ok=True)
    path = os.path.join(config.CURRENT, f"{index_id}.json")
    payload = {
        "index": index_id,
        "name": name,
        "category": category,
        "members": sorted(
            ({"symbol": m["symbol"], "name": m["name"], "isin": m.get("isin")}
             for m in members),
            key=lambda m: m["symbol"],
        ),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)


def _append_change(record):
    os.makedirs(config.DATA, exist_ok=True)
    with open(config.CHANGES, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def reconcile(index_id, name, category, new_members, detect_date):
    """Apply guards + diff for one index. Returns a status dict for meta.json.

    status: "initial" | "changed" | "unchanged" | "guarded"
    """
    new_by_sym = {m["symbol"]: m for m in new_members}
    new_syms = set(new_by_sym)
    prev = _read_current(index_id)

    # --- Snapshot guard ---
    if len(new_syms) < config.GUARD_MIN_MEMBERS:
        return {"status": "guarded", "reason": "empty fetch",
                "count": 0, "prev_count": len(prev["members"]) if prev else 0}
    if prev:
        prev_count = len(prev["members"])
        if prev_count > 0:
            drop = (prev_count - len(new_syms)) / prev_count
            if drop > config.GUARD_DROP_FRACTION:
                return {"status": "guarded",
                        "reason": f"shrank {drop:.0%} ({prev_count}->{len(new_syms)})",
                        "count": len(new_syms), "prev_count": prev_count}

    # --- First-run baseline ---
    if prev is None:
        _write_current(index_id, name, category, new_members)
        _append_change({
            "date": detect_date, "index": index_id, "name": name,
            "category": category, "type": "initial",
            "added": sorted(new_syms), "removed": [],
            "count": len(new_syms),
        })
        return {"status": "initial", "count": len(new_syms), "prev_count": 0}

    # --- Diff ---
    prev_syms = {m["symbol"] for m in prev["members"]}
    added = sorted(new_syms - prev_syms)
    removed = sorted(prev_syms - new_syms)
    name_changed = (prev.get("name") != name)
    members_changed = bool(added or removed)

    if not members_changed and not name_changed:
        return {"status": "unchanged", "count": len(new_syms),
                "prev_count": len(prev_syms)}

    # Write the new snapshot (covers membership and/or name/category updates).
    _write_current(index_id, name, category, new_members)

    if members_changed:
        prev_by_sym = {m["symbol"]: m for m in prev["members"]}
        _append_change({
            "date": detect_date, "index": index_id, "name": name,
            "category": category, "type": "change",
            "added": [{"symbol": s, "name": new_by_sym[s]["name"]} for s in added],
            "removed": [{"symbol": s, "name": prev_by_sym[s]["name"]} for s in removed],
            "count": len(new_syms),
        })
        return {"status": "changed", "count": len(new_syms),
                "prev_count": len(prev_syms),
                "added": len(added), "removed": len(removed)}

    # Only metadata (name) changed — snapshot updated, no changes.jsonl entry.
    return {"status": "unchanged", "count": len(new_syms),
            "prev_count": len(prev_syms), "note": "name updated"}
